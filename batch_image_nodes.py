"""
ComfyUI Custom Node: Batch Image Loader
This node loads all images from a folder and passes them one by one through the workflow
"""

import os
import numpy as np
from PIL import Image
import torch
import folder_paths

class BatchImageLoaderNode:
    """
    A node that loads all images from a folder and outputs them as a batch
    Each image will be processed through the workflow automatically
    """
    
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(s):
        # Get the input directory from ComfyUI
        input_dir = folder_paths.get_input_directory()
        
        return {
            "required": {
                "folder_path": ("STRING", {
                    "multiline": False,
                    "default": input_dir
                }),
                "image_extensions": ("STRING", {
                    "multiline": False,
                    "default": "png,jpg,jpeg,webp,bmp,gif"
                }),
                "sort_by": (["name", "modified", "created"], {
                    "default": "name"
                }),
            },
            "optional": {
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 10000
                }),
                "max_images": ("INT", {
                    "default": 0,  # 0 means all images
                    "min": 0,
                    "max": 10000
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "STRING", "INT",)
    RETURN_NAMES = ("images", "filenames", "count",)
    OUTPUT_NODE = False
    OUTPUT_IS_LIST = (True, True, False,)
    
    FUNCTION = "load_images"
    CATEGORY = "Skeba AI Nodes - Utilities"
    
    def load_images(self, folder_path, image_extensions="png,jpg,jpeg,webp,bmp,gif", 
                    sort_by="name", start_index=0, max_images=0):
        """
        Load all images from a folder
        
        Args:
            folder_path: Path to the folder containing images
            image_extensions: Comma-separated list of allowed extensions
            sort_by: How to sort files (name, modified, created)
            start_index: Skip first N images
            max_images: Maximum number of images to load (0 = all)
        
        Returns:
            tuple: (list of image tensors, list of filenames, count)
        """
        # Parse extensions
        extensions = [ext.strip().lower() for ext in image_extensions.split(',')]
        extensions = [f".{ext}" if not ext.startswith('.') else ext for ext in extensions]
        
        # Check if folder exists
        if not os.path.exists(folder_path):
            print(f"[BatchImageLoader] Folder not found: {folder_path}")
            return ([], [], 0)
        
        if not os.path.isdir(folder_path):
            print(f"[BatchImageLoader] Path is not a directory: {folder_path}")
            return ([], [], 0)
        
        # Get all image files
        image_files = []
        for filename in os.listdir(folder_path):
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in extensions:
                full_path = os.path.join(folder_path, filename)
                if os.path.isfile(full_path):
                    image_files.append({
                        'path': full_path,
                        'name': filename
                    })
        
        if not image_files:
            print(f"[BatchImageLoader] No images found in: {folder_path}")
            return ([], [], 0)
        
        # Sort files
        if sort_by == "name":
            image_files.sort(key=lambda x: x['name'])
        elif sort_by == "modified":
            image_files.sort(key=lambda x: os.path.getmtime(x['path']))
        elif sort_by == "created":
            image_files.sort(key=lambda x: os.path.getctime(x['path']))
        
        # Apply start_index and max_images
        if start_index > 0:
            image_files = image_files[start_index:]
        
        if max_images > 0 and len(image_files) > max_images:
            image_files = image_files[:max_images]
        
        # Load images
        images = []
        filenames = []
        
        for img_info in image_files:
            try:
                img = Image.open(img_info['path'])
                
                # Convert to RGB if necessary
                if img.mode == 'I':
                    img = img.point(lambda i: i * (1 / 255))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Convert to tensor (same format as ComfyUI's LoadImage node)
                img_array = np.array(img).astype(np.float32) / 255.0
                img_tensor = torch.from_numpy(img_array)[None,]
                
                images.append(img_tensor)
                filenames.append(img_info['name'])
                
            except Exception as e:
                print(f"[BatchImageLoader] Error loading {img_info['name']}: {str(e)}")
                continue
        
        count = len(images)
        print(f"[BatchImageLoader] Loaded {count} images from {folder_path}")
        
        return (images, filenames, count)


class ImageFromBatchNode:
    """
    A node that extracts a single image from a batch by index
    Useful for manual iteration or testing specific images
    """
    
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"forceInput": True}),
                "index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 10000
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "INT",)
    RETURN_NAMES = ("image", "index",)
    OUTPUT_NODE = False
    INPUT_IS_LIST = True
    
    FUNCTION = "get_image"
    CATEGORY = "Skeba AI Nodes - Utilities"
    
    def get_image(self, images, index):
        """
        Get a specific image from the batch by index
        
        Args:
            images: List of image tensors
            index: Index to retrieve (0-based)
        
        Returns:
            Single image tensor and its index
        """
        # Handle the input format
        if isinstance(index, list):
            index = index[0]
        
        if isinstance(images, list) and len(images) > 0:
            # Make sure index is within bounds
            actual_index = index % len(images)
            return (images[actual_index], actual_index)
        
        # Return empty tensor if no images
        empty_tensor = torch.zeros((1, 64, 64, 3))
        return (empty_tensor, 0)


