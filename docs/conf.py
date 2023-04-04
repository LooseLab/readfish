# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "readfish"
copyright = "Loose Lab"
author = "Loose Lab"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

master_doc = "index"

extensions = [
    "sphinx.ext.todo",
    # "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.autodoc",
    "sphinx.ext.autodoc.typehints",
    "myst_parser",
    "sphinx_copybutton",
]

myst_enable_extensions = [
    "colon_fence",
    "smartquotes",
    "deflist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

pygments_dark_style = "monokai"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}
add_function_parentheses = False

html_theme = "furo"
html_static_path = ["_static"]
html_theme_options = {
    "sidebar_hide_name": True,
}
html_theme_options = {
    "light_logo": "readfish_light.png",
    "dark_logo": "readfish_dark.png",
    "light_css_variables": {
        "font-stack": "Roboto, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif, Apple Color Emoji, Segoe UI Emoji",
        "font-stack--monospace": "'Ubuntu Mono', monospace",
        "code-font-size": "90%",
        "color-api-background": "#f8f9fb",
        "color-highlight-on-target": "transparent",
    },
    "dark_css_variables": {
        "color-api-background": "#1a1c1e",
        "color-highlight-on-target": "transparent",
    },
}
