import pandas as pd
import pandas as pd
import matplotlib.pyplot as plt

# ======================
# LOAD SAVED TIMELINE
# ======================
timeline_df = pd.read_csv("5000_number_date_progress_timeline.csv")

# Clean data
timeline_df = timeline_df.dropna(subset=["date", "avg_progress", "top_avg_progress"])
timeline_df["date"] = pd.to_datetime(timeline_df["date"])

# ======================
# VISUALIZATION
# ======================
print("📈 Visualizing pattern trend...")

plt.figure(figsize=(12, 6))
plt.plot(timeline_df["date"], timeline_df["avg_progress"], label="Avg Progress (%)", linewidth=2)
plt.plot(timeline_df["date"], timeline_df["top_avg_progress"], label="Top 10 Avg Progress (%)", linewidth=2, linestyle="--")

plt.xlabel("Date")
plt.ylabel("Progress toward 12× appearances (%)")
plt.title("🎯 Kerala Lottery ₹5000 Prize Number Repeat Trend (2020–Present)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.legend()
plt.tight_layout()
plt.show()

