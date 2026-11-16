"""Fixtures for SEM_crystal_counter's tests. Images are synthetic; the real SEM data never
enters the repo."""

import io

import numpy as np
import pytest
from PIL import Image
from scipy.spatial import cKDTree
from skimage import segmentation

# Every module the tests use, loaded in one go so they share their module objects (a
# monkeypatch on data_manager is seen by gui_components). tuner.py (streamlit) and
# legacy.py (OpenCV) are dev tools whose packages the app does not install.
MODULES = [
    "grain_core",
    "run_batch",
    "evaluate",
    "evaluate_cross_section",
    "training_log",
    "cross_section",
    "data_manager",
    "plot_manager",
    "gui_components",
    "app",
]


@pytest.fixture(scope="module")
def mods(app_loader):
    return app_loader("SEM_crystal_counter", MODULES)


def tiff_bytes(image: np.ndarray, metadata: bytes = b"") -> bytes:
    """A grayscale TIFF with free text appended, the way the Zeiss tag text sits in the file."""
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="TIFF")
    return buffer.getvalue() + metadata


@pytest.fixture
def make_tiff():
    return tiff_bytes


@pytest.fixture(scope="session")
def voronoi_film():
    """(image, true_labels): 30 grains with dark 3 px grooves, noisy, 5 nm/px."""
    rng = np.random.default_rng(7)
    height, width = 300, 400
    centers = rng.uniform((0, 0), (height, width), size=(30, 2))
    yy, xx = np.mgrid[:height, :width]
    _, nearest = cKDTree(centers).query(np.column_stack([yy.ravel(), xx.ravel()]))
    labels = nearest.reshape(height, width) + 1
    shades = rng.uniform(120, 160, size=labels.max() + 1)
    image = shades[labels]
    grooves = segmentation.find_boundaries(labels, mode="thick")
    image[grooves] = 70
    image = image + rng.normal(0, 6, size=image.shape)
    return np.clip(image, 0, 255).astype(np.uint8), labels


def cross_section_image(top_row=100, film_rows=200, seed=0) -> np.ndarray:
    """Vacuum (dark, smooth) / grainy film / bright interface line / smooth substrate."""
    rng = np.random.default_rng(seed)
    height, width = 420, 500
    img = np.full((height, width), 60.0) + rng.normal(0, 1, (height, width))
    bottom = top_row + film_rows
    # Voronoi grains: no grain edges lined up across the width (those would look like an
    # interface, which real grains never do)
    centres = rng.uniform((0, 0), (film_rows, width), size=(40, 2))
    yy, xx = np.mgrid[:film_rows, :width]
    _, nearest = cKDTree(centres).query(np.column_stack([yy.ravel(), xx.ravel()]))
    film = rng.uniform(110, 170, size=40)[nearest.reshape(film_rows, width)]
    img[top_row:bottom] = film + rng.normal(0, 8, film.shape)
    img[bottom : bottom + 4] = 220
    img[bottom + 4 :] = 140 + rng.normal(0, 1, (height - bottom - 4, width))
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.fixture
def cross_section():
    """Function (top_row, film_rows, seed) -> synthetic cross-section image, 5 nm/px."""
    return cross_section_image
