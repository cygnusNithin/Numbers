import cv2, json, re, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk

try:
    import easyocr
    OCR = easyocr.Reader(["en"], gpu=False)
except Exception:
    OCR = None

CONFIG_DIR = Path(__file__).resolve().parent / "video_configs"
OUTPUT_DIR = Path(__file__).resolve().parent / "inspection_results"


class LotteryVideoWorkflow:
    REGIONS = ["Machine body", "Roller", "Yellow label", "Category", "Serial", "Red light"]

    def __init__(self, root):
        self.root = root
        root.title("Lottery Machine Video Workflow")
        root.geometry("1500x900")
        self.cap = self.video_path = self.frame = None
        self.fps, self.frame_index, self.playing = 30.0, 0, False
        self.play_job = None
        self.config_path = None
        self.machine_config = {"positions": {"A": self.empty_layout(), "B": self.empty_layout()}}
        self.active_position = tk.StringVar(value="A")
        self.roi_history, self.roi_target = [], None
        self.roi_drawing, self.drag_start, self.drag_end = False, None, None
        self.scale, self.offset, self.image = 1.0, (0, 0), None
        self.inspection_active, self.expected_count, self.results = False, 18, []
        self.roller_events, self.red_events = [], []
        self.prev_roller = {"A": {}, "B": {}}
        self.closeup_frames = set()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def empty_layout():
        return {"machine_body": None, "rollers": {}, "yellow_labels": {},
                "category": None, "serial": None, "red_light": None}

    @staticmethod
    def next_number(mapping):
        for n in range(1, 19):
            if str(n) not in mapping:
                return n
        return None

    def build_ui(self):
        top = ttk.Frame(self.root); top.pack(fill="x", padx=8, pady=7)
        for label, fn in [("Select Video", self.select_video), ("Play / Pause", self.toggle_play),
                          ("−10 sec", lambda: self.seek_seconds(-10)), ("+10 sec", lambda: self.seek_seconds(10)),
                          ("Previous Frame", lambda: self.seek_frames(-1)), ("Next Frame", lambda: self.seek_frames(1))]:
            ttk.Button(top, text=label, command=fn).pack(side="left", padx=2)
        self.video_label = ttk.Label(top, text="No video"); self.video_label.pack(side="left", padx=8)
        main = ttk.Frame(self.root); main.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(main, bg="#151515", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(main, width=360); side.pack(side="right", fill="y", padx=8, pady=4); side.pack_propagate(False)
        ttk.Label(side, text="PASS 1 — MACHINE CONFIGURATION", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(side, text="ROI Position").pack(anchor="w")
        self.position_box = ttk.Combobox(side, textvariable=self.active_position, values=["A", "B"], state="readonly")
        self.position_box.pack(fill="x", pady=2); self.position_box.bind("<<ComboboxSelected>>", lambda e: self.status_refresh())
        ttk.Label(side, text="ROI Region").pack(anchor="w")
        self.region_box = ttk.Combobox(side, values=self.REGIONS, state="readonly"); self.region_box.current(0); self.region_box.pack(fill="x", pady=2)
        ttk.Button(side, text="Draw Selected ROI", command=self.begin_roi).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove Last Mark", command=self.undo_roi).pack(fill="x", pady=2)
        ttk.Button(side, text="Save Machine Configuration", command=self.save_config).pack(fill="x", pady=2)
        ttk.Button(side, text="Load Machine Configuration", command=self.load_config).pack(fill="x", pady=2)
        self.config_status = ttk.Label(side, text="A: 0/40 | B: 0/40", wraplength=340); self.config_status.pack(anchor="w", pady=5)
        ttk.Separator(side).pack(fill="x", pady=8)
        ttk.Label(side, text="PASS 2 — INSPECTION", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Button(side, text="Start / Reset Inspection", command=self.start_inspection).pack(fill="x", pady=2)
        ttk.Label(side, text="Expected number count").pack(anchor="w")
        self.expected_var = tk.StringVar(value="18"); ttk.Entry(side, textvariable=self.expected_var).pack(fill="x", pady=2)
        ttk.Button(side, text="Inspect Current Frame", command=self.inspect_frame).pack(fill="x", pady=2)
        ttk.Button(side, text="Extract Number From Close-up", command=self.extract_number).pack(fill="x", pady=2)
        ttk.Button(side, text="Export Inspection Results", command=self.export_results).pack(fill="x", pady=2)
        self.inspect_status = ttk.Label(side, text="Load configuration, then select inspection video.", wraplength=340); self.inspect_status.pack(anchor="w", pady=5)
        self.result_box = tk.Text(side, height=18, wrap="word"); self.result_box.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<ButtonPress-1>", self.mouse_down); self.canvas.bind("<B1-Motion>", self.mouse_move); self.canvas.bind("<ButtonRelease-1>", self.mouse_up)

    # Video
    def select_video(self):
        p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")])
        if not p: return
        self.stop_play()
        if self.cap: self.cap.release()
        self.cap = cv2.VideoCapture(p)
        if not self.cap.isOpened(): messagebox.showerror("Video", "Cannot open video."); return
        self.video_path = Path(p); self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.video_label.config(text=self.video_path.name); self.read_frame(0)
        if self.config_path: self.inspect_status.config(text="Configuration loaded. Video selected; start inspection.")

    def read_frame(self, i):
        if not self.cap: return
        total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1); i = max(0, min(int(i), total-1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = self.cap.read()
        if ok: self.frame, self.frame_index = f, i; self.render()

    def seek_seconds(self, s): self.read_frame(self.frame_index + int(s*self.fps))
    def seek_frames(self, n): self.read_frame(self.frame_index+n)
    def toggle_play(self):
        if self.playing: self.stop_play()
        else: self.playing = True; self.play_loop()
    def stop_play(self):
        self.playing = False
        if self.play_job:
            try: self.root.after_cancel(self.play_job)
            except tk.TclError: pass
            self.play_job = None
    def play_loop(self):
        if not self.playing: return
        total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if self.frame_index+1 >= total: self.stop_play(); return
        self.read_frame(self.frame_index+1); self.play_job = self.root.after(max(1,int(1000/self.fps)),self.play_loop)

    # ROI auto numbering, two positions, undo
    def begin_roi(self):
        if self.frame is None: messagebox.showwarning("Video","Select reference video first."); return
        pos, kind = self.active_position.get(), self.region_box.get()
        layout = self.machine_config["positions"][pos]
        if kind == "Roller":
            n = self.next_number(layout["rollers"])
            if n is None: messagebox.showinfo("Complete","18 rollers already marked."); return
            self.roi_target = ("rollers",str(n))
        elif kind == "Yellow label":
            n = self.next_number(layout["yellow_labels"])
            if n is None: messagebox.showinfo("Complete","18 labels already marked."); return
            self.roi_target = ("yellow_labels",str(n))
        else:
            key = {"Machine body":"machine_body","Category":"category","Serial":"serial","Red light":"red_light"}[kind]
            self.roi_target = (key,None)
        self.roi_drawing=True; self.drag_start=self.drag_end=None
        self.inspect_status.config(text=f"Draw Position {pos}: {self.roi_target[0]} {self.roi_target[1] or ''}")

    def mouse_down(self,e):
        if self.roi_drawing: self.drag_start=self.drag_end=(e.x,e.y)
    def mouse_move(self,e):
        if self.roi_drawing and self.drag_start: self.drag_end=(e.x,e.y); self.render()
    def mouse_up(self,e):
        if not self.roi_drawing or not self.drag_start or self.frame is None: return
        self.drag_end=(e.x,e.y); x1,y1=self.drag_start; x2,y2=self.drag_end; ox,oy=self.offset
        x=int((min(x1,x2)-ox)/self.scale); y=int((min(y1,y2)-oy)/self.scale)
        w=int(abs(x2-x1)/self.scale); h=int(abs(y2-y1)/self.scale); fh,fw=self.frame.shape[:2]
        x=max(0,min(x,fw-1)); y=max(0,min(y,fh-1)); w=max(1,min(w,fw-x)); h=max(1,min(h,fh-y))
        if w<3 or h<3: self.roi_drawing=False; self.drag_start=self.drag_end=None; self.render(); return
        pos=self.active_position.get(); key,idx=self.roi_target; layout=self.machine_config["positions"][pos]
        old=layout[key].get(idx) if idx is not None else layout[key]
        if idx is not None: layout[key][idx]=[x,y,w,h]
        else: layout[key]=[x,y,w,h]
        self.roi_history.append({"position":pos,"key":key,"index":idx,"old":old})
        self.roi_drawing=False; self.drag_start=self.drag_end=None; self.status_refresh(); self.render()

    def undo_roi(self):
        if not self.roi_history: messagebox.showinfo("Undo","No ROI marks to remove."); return
        item=self.roi_history.pop(); layout=self.machine_config["positions"][item["position"]]
        key,idx,old=item["key"],item["index"],item["old"]
        if idx is not None:
            if old is None: layout[key].pop(idx,None)
            else: layout[key][idx]=old
        else: layout[key]=old
        self.status_refresh(); self.render()

    def status_refresh(self):
        def count(l): return sum(l[k] is not None for k in ("machine_body","category","serial","red_light"))+len(l["rollers"])+len(l["yellow_labels"])
        self.config_status.config(text=f"A: {count(self.machine_config['positions']['A'])}/40 | B: {count(self.machine_config['positions']['B'])}/40")

    # Save/load config (supports previous one-layout config)
    def save_config(self):
        if self.frame is None or not self.video_path: messagebox.showwarning("Reference","Select reference video."); return
        CONFIG_DIR.mkdir(parents=True,exist_ok=True)
        p=filedialog.asksaveasfilename(initialdir=str(CONFIG_DIR),initialfile=f"{self.video_path.stem}_machine.json",defaultextension=".json",filetypes=[("JSON","*.json")])
        if not p:return
        data={"configuration_version":3,"machine_config":self.machine_config,"reference_video":{"filename":self.video_path.name,"width":self.frame.shape[1],"height":self.frame.shape[0]},"updated_at":datetime.now().isoformat()}
        try: Path(p).write_text(json.dumps(data,indent=2),encoding="utf-8"); self.config_path=str(Path(p).resolve()); messagebox.showinfo("Saved","Both Position A and B saved.")
        except Exception as e: messagebox.showerror("Save",str(e))

    def load_config(self):
        CONFIG_DIR.mkdir(parents=True,exist_ok=True); p=filedialog.askopenfilename(initialdir=str(CONFIG_DIR),filetypes=[("JSON","*.json")])
        if not p:return
        try:
            data=json.loads(Path(p).read_text(encoding="utf-8")); cfg=data.get("machine_config",{})
            if "positions" not in cfg:
                old=cfg; cfg={"positions":{"A":self.empty_layout(),"B":self.empty_layout()}}
                for k in self.empty_layout():
                    cfg["positions"]["A"][k]=old.get(k,{} if k in ("rollers","yellow_labels") else None)
            for pos in ("A","B"):
                cfg["positions"].setdefault(pos,self.empty_layout())
                for k,v in self.empty_layout().items(): cfg["positions"][pos].setdefault(k,{} if k in ("rollers","yellow_labels") else None)
            self.machine_config=cfg; self.config_path=str(Path(p).resolve()); self.roi_history.clear(); self.status_refresh(); self.render()
            self.inspect_status.config(text="Configuration loaded. Select inspection video next.")
            messagebox.showinfo("Loaded","Position A and B loaded.")
        except Exception as e: messagebox.showerror("Config",str(e))

    # Pass 2
    def start_inspection(self):
        if not self.config_path: messagebox.showwarning("Config","Load saved machine configuration first."); return
        if not self.cap or self.frame is None: messagebox.showwarning("Video","Select inspection video after loading config."); return
        try: self.expected_count=int(self.expected_var.get()); assert self.expected_count>0
        except Exception: messagebox.showwarning("Count","Expected count must be positive."); return
        self.results=[]; self.roller_events=[]; self.red_events=[]; self.prev_roller={"A":{},"B":{}}; self.closeup_frames=set(); self.inspection_active=True
        self.inspect_status.config(text=f"Inspection active: 0/{self.expected_count}"); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)

    def select_position(self,frame):
        scores={}
        for pos,l in self.machine_config["positions"].items():
            roi=l.get("machine_body")
            if not roi: scores[pos]=-1; continue
            x,y,w,h=roi; crop=frame[y:y+h,x:x+w]
            if crop.size==0:scores[pos]=-1;continue
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); scores[pos]=float(cv2.Canny(gray,60,120).mean())
        return max(scores,key=scores.get)

    def inspect_frame(self):
        if not self.inspection_active or self.frame is None: messagebox.showwarning("Inspection","Start inspection first."); return
        pos=self.select_position(self.frame); layout=self.machine_config["positions"][pos]
        red=self.red_detect(self.frame,layout.get("red_light")); moving=self.roller_motion(self.frame,pos,layout["rollers"])
        close=self.closeup_detect(self.frame,layout.get("machine_body"))
        self.red_events.append({"frame":self.frame_index,"position":pos,"red_on":red})
        self.roller_events.append({"frame":self.frame_index,"position":pos,"moving_rollers":moving})
        if close and self.frame_index not in self.closeup_frames:self.save_closeup(self.frame,pos);self.closeup_frames.add(self.frame_index)
        self.inspect_status.config(text=f"Position {pos} | frame {self.frame_index} | red={red} | moving={moving} | close-up={close} | results {len(self.results)}/{self.expected_count}")

    @staticmethod
    def red_detect(frame,roi):
        if not roi:return False
        x,y,w,h=roi; crop=frame[y:y+h,x:x+w]
        if crop.size==0:return False
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV); a=cv2.inRange(hsv,(0,90,90),(12,255,255)); b=cv2.inRange(hsv,(165,90,90),(180,255,255))
        return cv2.countNonZero(cv2.bitwise_or(a,b))/max(1,crop.shape[0]*crop.shape[1])>=0.05

    def roller_motion(self,frame,pos,rollers):
        moving=[]; prev=self.prev_roller[pos]
        for idx,roi in rollers.items():
            x,y,w,h=roi; crop=frame[y:y+h,x:x+w]
            if crop.size==0:continue
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); old=prev.get(idx)
            if old is not None and old.shape==gray.shape:
                diff=cv2.absdiff(gray,old); mask=cv2.threshold(diff,22,255,cv2.THRESH_BINARY)[1]
                if cv2.countNonZero(mask)/max(1,w*h)>0.06:moving.append(int(idx))
            prev[idx]=gray
        return moving

    @staticmethod
    def closeup_detect(frame,body):
        if not body:return False
        x,y,w,h=body; crop=frame[y:y+h,x:x+w]
        return crop.size>0 and (w*h)/(frame.shape[0]*frame.shape[1])>0.30

    def save_closeup(self,frame,pos):
        OUTPUT_DIR.mkdir(parents=True,exist_ok=True); cv2.imwrite(str(OUTPUT_DIR/f"closeup_{pos}_{self.frame_index:08d}.jpg"),frame)

    def extract_number(self):
        if not self.inspection_active or self.frame is None:messagebox.showwarning("Inspection","Start inspection first.");return
        if len(self.results)>=self.expected_count:messagebox.showinfo("Complete","Expected count reached.");return
        pos=self.select_position(self.frame); roi=self.machine_config["positions"][pos].get("category")
        if not roi:messagebox.showwarning("ROI",f"Position {pos} category ROI missing.");return
        x,y,w,h=roi; crop=self.frame[y:y+h,x:x+w]
        candidates=[]
        if OCR:
            for _,txt,conf in OCR.readtext(crop):
                digits=re.sub(r"\\D","",txt)
                if len(digits)==4:candidates.append((digits,float(conf)))
        if candidates:number,confidence=max(candidates,key=lambda z:z[1])
        else:
            number=simpledialog.askstring("Number","OCR unavailable/failed. Enter four digits:")
            if not number or not re.fullmatch(r"\\d{4}",number.strip()):return
            number=number.strip(); confidence=0.0
        item={"sequence":len(self.results)+1,"number":number,"confidence":confidence,"frame":self.frame_index,"time_seconds":round(self.frame_index/self.fps,3),"position":pos}
        self.results.append(item);self.result_box.insert("end",f"{item['sequence']:02d}: {number} confidence={confidence:.3f} frame={self.frame_index}\\n");self.result_box.see("end")
        self.inspect_status.config(text=f"{len(self.results)}/{self.expected_count} numbers captured")
        if len(self.results)>=self.expected_count:self.inspection_active=False;self.inspect_status.config(text=f"COMPLETE: {len(self.results)}/{self.expected_count}");messagebox.showinfo("Complete","Expected count reached.")

    def export_results(self):
        if not self.video_path:messagebox.showwarning("Video","Select inspection video.");return
        OUTPUT_DIR.mkdir(parents=True,exist_ok=True); p=filedialog.asksaveasfilename(initialdir=str(OUTPUT_DIR),defaultextension=".json",initialfile="inspection_results.json",filetypes=[("JSON","*.json")])
        if not p:return
        data={"video":str(self.video_path),"configuration":self.config_path,"expected_count":self.expected_count,"result_count":len(self.results),"results":self.results,"roller_events":self.roller_events,"red_light_events":self.red_events}
        Path(p).write_text(json.dumps(data,indent=2),encoding="utf-8");messagebox.showinfo("Export",f"Saved {p}")

    # Render
    def render(self):
        if not hasattr(self,"canvas") or self.frame is None:return
        self.canvas.delete("all"); cw,ch=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height()); fh,fw=self.frame.shape[:2]
        self.scale=min(cw/fw,ch/fh); dw,dh=int(fw*self.scale),int(fh*self.scale); ox,oy=(cw-dw)//2,(ch-dh)//2;self.offset=(ox,oy)
        rgb=cv2.cvtColor(cv2.resize(self.frame,(dw,dh)),cv2.COLOR_BGR2RGB);self.image=ImageTk.PhotoImage(Image.fromarray(rgb));self.canvas.create_image(ox,oy,anchor="nw",image=self.image)
        for pos,layout in self.machine_config["positions"].items():
            color="#ffe600" if pos=="A" else "#00e5ff"
            for key,val in layout.items():
                if key in ("rollers","yellow_labels"):
                    for idx,box in val.items():self.draw_roi(f"{pos}:{key}:{idx}",box,color)
                elif val:self.draw_roi(f"{pos}:{key}",val,color)
        if self.roi_drawing and self.drag_start and self.drag_end:self.canvas.create_rectangle(*self.drag_start,*self.drag_end,outline="red",width=2)

    def draw_roi(self,label,roi,color):
        x,y,w,h=roi;ox,oy=self.offset;s=self.scale
        self.canvas.create_rectangle(ox+x*s,oy+y*s,ox+(x+w)*s,oy+(y+h)*s,outline=color,width=2)
        self.canvas.create_text(ox+x*s+2,oy+y*s+2,text=label,anchor="nw",fill=color,font=("Segoe UI",8,"bold"))

    def close(self):
        self.stop_play()
        if self.cap:self.cap.release()
        self.root.destroy()


if __name__=="__main__":
    root=tk.Tk()
    LotteryVideoWorkflow(root)
    root.mainloop()
