#!/usr/bin/env python3
# train_digit_cnn.py
import os, argparse
import numpy as np
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv2D, MaxPool2D, Flatten, Dense, Dropout, BatchNormalization
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.optimizers import Adam
import cv2, glob

ap = argparse.ArgumentParser()
ap.add_argument("--data_dir", default="digit_crops/labeled")
ap.add_argument("--img_size", type=int, default=40)
ap.add_argument("--batch", type=int, default=64)
ap.add_argument("--epochs", type=int, default=40)
ap.add_argument("--model_out", default="digit_model.h5")
args = ap.parse_args()

# Build dataset arrays
X = []
y = []
for lbl in sorted(os.listdir(args.data_dir)):
    lbl_dir = os.path.join(args.data_dir, lbl)
    if not os.path.isdir(lbl_dir): continue
    if not lbl.isdigit(): continue
    for f in glob.glob(os.path.join(lbl_dir, "*.png")):
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        img = cv2.resize(img, (args.img_size, args.img_size))
        # normalize
        img = cv2.equalizeHist(img)
        img = img.astype("float32") / 255.0
        X.append(img[..., None])
        y.append(int(lbl))

X = np.array(X)
y = np.array(y)
print("X shape", X.shape, "y shape", y.shape)

# shuffle
idx = np.arange(len(X))
np.random.shuffle(idx)
X = X[idx]; y = y[idx]

# split
n = len(X)
split = int(n*0.8)
X_train, X_val = X[:split], X[split:]
y_train, y_val = y[:split], y[split:]

# datagen
datagen = ImageDataGenerator(
    rotation_range=6,
    width_shift_range=0.08,
    height_shift_range=0.08,
    shear_range=0.05,
    zoom_range=0.08
)

train_gen = datagen.flow(X_train, to_categorical(y_train,10), batch_size=args.batch)

# model
model = Sequential([
    Conv2D(32, (3,3), activation="relu", input_shape=(args.img_size, args.img_size,1)),
    BatchNormalization(),
    Conv2D(32,(3,3),activation="relu"),
    MaxPool2D(),
    Dropout(0.2),

    Conv2D(64,(3,3),activation="relu"),
    BatchNormalization(),
    Conv2D(64,(3,3),activation="relu"),
    MaxPool2D(),
    Dropout(0.25),

    Flatten(),
    Dense(128, activation="relu"),
    Dropout(0.4),
    Dense(10, activation="softmax")
])

model.compile(optimizer=Adam(1e-3), loss="categorical_crossentropy", metrics=["accuracy"])
model.summary()

callbacks = [
    ModelCheckpoint(args.model_out, save_best_only=True, monitor="val_accuracy", mode="max"),
    EarlyStopping(monitor="val_accuracy", patience=8, restore_best_weights=True),
    ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4)
]

steps_per_epoch = max(10, len(X_train)//args.batch)
model.fit(train_gen, steps_per_epoch=steps_per_epoch, epochs=args.epochs,
          validation_data=(X_val, to_categorical(y_val,10)), callbacks=callbacks)

# If best model saved by callback, it's already at args.model_out
print("Training finished. Best model saved to", args.model_out)
