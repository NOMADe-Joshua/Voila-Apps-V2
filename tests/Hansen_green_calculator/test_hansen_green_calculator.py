"""Smoke tests for Hansen_green_calculator: unifac_model, imported by the notebooks, loads.

The calculators themselves live in the notebooks, so only the local module is tested here.
"""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_functions_the_notebooks_use_are_present(mods):
    for name in [
        "calculate_overall_donor_number_with_unifac",
        "calculate_activity_coefficients_unifac",
    ]:
        assert hasattr(mods["unifac_model"], name), name
