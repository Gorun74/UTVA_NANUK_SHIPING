from pathlib import Path


def get_item_images(sku: str, image_root: str) -> list:
    """Returns sorted list of image Paths for a given SKU."""
    folder = Path(image_root) / sku
    if not folder.exists():
        return []
    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    return sorted(f for f in folder.iterdir() if f.suffix.lower() in exts)


def get_thumbnail(sku: str, image_root: str):
    """Returns _1.jpg as thumbnail, fallback to first found. None if none."""
    primary = Path(image_root) / sku / f"{sku}_1.jpg"
    if primary.exists():
        return primary
    imgs = get_item_images(sku, image_root)
    return imgs[0] if imgs else None
