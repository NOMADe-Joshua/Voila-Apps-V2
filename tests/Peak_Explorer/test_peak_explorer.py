"""Smoke tests for Peak_Explorer: the pl_* modules main_notebook.ipynb imports load.

The app class itself lives in the notebook, so only its local modules are tested here.
"""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_classes_the_notebook_uses_are_present(mods):
    expected = {
        "pl_data_loader": "PLDataLoader",
        "pl_fitting_models": "PLFittingModels",
        "pl_visualization": "PLVisualization",
        "pl_peak_detection": "PLPeakDetection",
        "pl_export_utils": "PLExportUtils",
    }
    for module, cls in expected.items():
        assert hasattr(mods[module], cls), f"{module}.{cls}"
