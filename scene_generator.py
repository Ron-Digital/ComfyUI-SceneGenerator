import json
import base64
from PIL import Image, ImageOps, ImageChops
from io import BytesIO
import requests
import numpy as np

class SceneGenerator:
    @staticmethod
    def INPUT_TYPES():
        return {
            "required": {
                "json_img": ("STRING", {"multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    FUNCTION = "process"

    def __init__(self):
        pass

    def process(self, json_img):
        try:
            if not json_img:
                raise ValueError("JSON input must not be empty")

            # Parse the JSON string
            try:
                json_data = json.loads(json_img)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {str(e)}")

            if "json_img" not in json_data:
                raise ValueError("Invalid JSON input: missing 'json_img' key")

            def sort_key(item):
                return item['config'].get('z', float('-inf'))

            data = json_data["json_img"]["json"]
            original_width = json_data["json_img"]["stage"]["width"]
            original_height = json_data["json_img"]["stage"]["height"]
            scale_factor = 1

            main_image = Image.new('RGBA', (original_width, original_height), (255, 255, 255, 255))
            product_image = Image.new('RGBA', (original_width, original_height), (255, 255, 255, 0))
            product_mask = Image.new('L', (original_width, original_height), 0)  # Alpha channel for the product

            sorted_data = sorted(data, key=sort_key)

            for item in sorted_data:
                config = item['config']

                if config["width"] == 0 or config["height"] == 0 or config["scale"]["x"] == 0 or config["scale"]["y"] == 0:
                    continue

                # Ölçeklendirme
                config["x"] *= scale_factor
                config["y"] *= scale_factor
                config["width"] *= scale_factor
                config["height"] *= scale_factor

                # Görüntüyü URL'den indirme ve yükleme
                image_url = config["src"]
                response = requests.get(image_url)
                image = Image.open(BytesIO(response.content))
                image = self.apply_flip(image, config["flip"])

                if image.mode != 'RGBA':
                    image = image.convert('RGBA')

                # Ayarlama ve döndürme
                new_width = int(image.width * config["scale"]["x"])
                new_height = int(image.height * config["scale"]["y"])
                image_resized = image.resize((new_width, new_height), Image.LANCZOS)
                center_x, center_y = new_width / 2, new_height / 2
                image_rotated = image_resized.rotate(-config["rotation"], center=(center_x, center_y), expand=True)

                # Döndürme sonrası yeni konum hesaplamaları
                rotated_width, rotated_height = image_rotated.size
                rotated_center_x, rotated_center_y = rotated_width / 2, rotated_height / 2
                new_x = config["x"] + center_x - rotated_center_x
                new_y = config["y"] + center_y - rotated_center_y

                # Koordinatları merkezleme
                paste_x = int(config["x"])
                paste_y = int(config["y"])

                if config["p_type"] == 'product':
                    product_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)
                    main_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)
                    
                    # Product maskesine ekleme
                    mask_to_add = Image.new('L', (rotated_width, rotated_height), 255)
                    product_mask.paste(mask_to_add, (int(new_x), int(new_y)))
                else:
                    main_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)

                    # Prop'un product maskesindeki etkisini kaldırma
                    mask_to_remove = image_rotated.split()[3]  # Alpha channel
                    mask_to_remove_resized = mask_to_remove.resize((rotated_width, rotated_height), Image.LANCZOS)
                    mask_to_remove_position = Image.new('L', (original_width, original_height), 0)
                    mask_to_remove_position.paste(mask_to_remove_resized, (int(new_x), int(new_y)))
                    product_mask = ImageChops.subtract(product_mask, mask_to_remove_position)

            # Apply the final product mask to the product image
            product_image = self.apply_transparency_mask(product_image, product_mask)

            # Convert images to base64
            product_image_base64 = self.image_to_base64(product_image)
            main_image_base64 = self.image_to_base64(main_image)

            return (product_image_base64, main_image_base64)

        except Exception as e:
            raise ValueError(f"An error occurred: {str(e)}")

    def apply_flip(self, image, flip):
        flip_x, flip_y = json.loads(flip)
        if flip_x == -1:
            image = ImageOps.mirror(image)
        if flip_y == -1:
            image = ImageOps.flip(image)
        return image

    def image_to_base64(self, image):
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_str

    def apply_transparency_mask(self, image, mask):
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        mask = mask.resize(image.size, Image.LANCZOS)
        alpha = image.split()[3]
        alpha = ImageChops.multiply(alpha, mask)
        image.putalpha(alpha)
        return image
