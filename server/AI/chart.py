import pandas as pd
import matplotlib.pyplot as plt

# Load prediction log
df = pd.read_csv("prediction_log.csv")

# Plot probabilities for each prize category
plt.figure(figsize=(10,6))
for col in ["prob_100","prob_500","prob_1000","prob_2000","prob_5000","prob_200"]:
    plt.plot(df.index, df[col], marker="o", label=col)

plt.title("Prediction Probabilities per Prize")
plt.xlabel("Sample Index")
plt.ylabel("Probability")
plt.legend()
plt.grid(True)
plt.show()
