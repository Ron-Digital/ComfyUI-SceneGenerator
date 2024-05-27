import base64
import json
import requests
from io import BytesIO
from PIL import Image, ImageOps, ImageChops
import numpy as np
import torch

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
            product_image = Image.new('RGBA', (original_width, original_height), (255, 255, 255, 255))

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

                # Image yükleme
                response = requests.get(config["src"])
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

                # Product image üzerine prop'ları yapıştırma ve gerektiğinde kesme
                if config["p_type"] == 'product':
                    product_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)
                    main_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)
                else:
                    main_image.paste(image_rotated, (int(new_x), int(new_y)), image_rotated)

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

    def crop_overlapping_area(self, product_image, prop_image, prop_x, prop_y):
        product_box = (prop_x, prop_y, prop_x + prop_image.width, prop_y + prop_image.height)
        region = product_image.crop(product_box)
        cropped_region = ImageChops.subtract(region, prop_image)
        product_image.paste(cropped_region, product_box)

    def image_to_base64(self, image):
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_str