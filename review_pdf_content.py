import fitz
doc = fitz.open('server/test/draw-75364.pdf')
for i, page in enumerate(doc):
    text = page.get_text()
    print(f'--- Page {i+1} Text ---')
    print(text)
    print()
doc.close()