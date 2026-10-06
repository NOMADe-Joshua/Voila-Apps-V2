"""Smoke tests for MPPT_Analysis: the helper modules mppt_plotting.ipynb imports load.

The app itself lives in the notebook (needs a token and the network), so only its local
modules are tested here.
"""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_names_the_notebook_uses_are_present(mods):
    for name in [
        "fit_model",
        "linear_params",
        "exponential_params",
        "biexponential_params",
        "logistic_params",
        "stretched_exponential_params",
        "erfc_params",
    ]:
        assert hasattr(mods["fitting_tools"], name), name
    assert hasattr(mods["font_size_ui"], "FontSizeUI")
