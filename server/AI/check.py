import torch
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader

# Apply basic transformations (resize + convert to tensor)
transform = transforms.Compose([
    transforms.Resize((64, 64)),   # resize all images to 64x64
    transforms.ToTensor()
])

# Load dataset from folders
train_data = torchvision.datasets.ImageFolder(root='dataset', transform=transform)

# Create a DataLoader (batches of images)
train_loader = DataLoader(train_data, batch_size=16, shuffle=True)

# Check class labels
print(train_data.classes)  # ['cats', 'dogs']
