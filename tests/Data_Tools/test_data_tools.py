"""Smoke tests for Data_Tools: the converter modules data_tools.ipynb imports load.

The dashboard itself lives in the notebook, so only its local modules are tested here.
"""


def test_modules_import(mods):
    for name, module in mods.items():
        assert module.__name__ == name


def test_names_the_notebook_uses_are_present(mods):
    expected = {
        "iv_converter_module": ["process_files"],
        "uvvis_merger_module": ["process_uvvis_files"],
        "jv_organizer_module": ["process_zip_file", "process_files"],
        "eln_renamer_module": ["process_files"],
        "eqe_split_module": ["parse_eqe_file", "process_eqe_file", "create_download_zip"],
    }
    for module, names in expected.items():
        for name in names:
            assert hasattr(mods[module], name), f"{module}.{name}"
