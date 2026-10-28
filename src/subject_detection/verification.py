from __future__ import annotations

import cv2
import numpy as np

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_INPUT_SIZE = 224


def masked_fill(img_bgr: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    if mask is None:
        return img_bgr
    m = mask
    if m.shape != img_bgr.shape[:2]:
        m = cv2.resize(m, (img_bgr.shape[1], img_bgr.shape[0]),
                       interpolation=cv2.INTER_LINEAR)
    m3 = m[..., None].astype(np.float32)
    wsum = max(float(m.sum()), 1e-6)
    mean = (img_bgr.astype(np.float32) * m3).reshape(-1, 3).sum(0) / wsum
    out = img_bgr.astype(np.float32) * m3 + mean * (1.0 - m3)
    return out.astype(np.uint8)


class Verifier:

    def __init__(self) -> None:
        import torch
        self._torch = torch
        # pin the branch: without it torch.hub asks GitHub for the default
        # branch on every load and raises on a 5xx (only a dead network
        # falls back to the cache), silently dropping us to coarse-only
        self._model = torch.hub.load("facebookresearch/dinov2:main",
                                     "dinov2_vits14", trust_repo=True,
                                     verbose=False)
        self._model.eval()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)

    def embed(self, imgs_bgr: list[np.ndarray]) -> np.ndarray:
        torch = self._torch
        batch = np.stack([self._preprocess(img) for img in imgs_bgr])
        with torch.inference_mode():
            t = torch.from_numpy(batch).to(self._device)
            emb = self._model(t).cpu().numpy().astype(np.float32)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        return emb / np.maximum(norms, 1e-9)

    @staticmethod
    def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (_INPUT_SIZE, _INPUT_SIZE),
                         interpolation=cv2.INTER_AREA
                         if rgb.shape[0] > _INPUT_SIZE else cv2.INTER_CUBIC)
        x = rgb.astype(np.float32) / 255.0
        x = (x - _IMAGENET_MEAN) / _IMAGENET_STD
        return x.transpose(2, 0, 1)
