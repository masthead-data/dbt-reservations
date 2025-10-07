import os

from jinja2 import Environment, FileSystemLoader


def render_macro(context, prefix=None):
    """Import the macro file and invoke the macro, passing the rendering context."""
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)
    # create a small wrapper template that imports the macro and calls it
    if prefix is None:
        prefix_arg = ""
    else:
        prefix_arg = "'{}'".format(prefix)
    wrapper = "{% from 'add_model_id_comment.sql' import add_model_id_comment %}\n"
    wrapper += "{{ add_model_id_comment(" + prefix_arg + ") }}\n"
    template = env.from_string(wrapper)
    # ensure macros can access these names during import/call
    env.globals.update(context)
    return template.render()


def test_macro_with_model_unique_id():
    from types import SimpleNamespace
    ctx = {'model': SimpleNamespace(unique_id='model.test_project.customers')}
    out = render_macro(ctx)
    assert 'model.test_project.customers' in out


def test_macro_with_this_identifier_fallback():
    from types import SimpleNamespace
    ctx = {'this': SimpleNamespace(identifier='customers')}
    out = render_macro(ctx)
    assert 'customers' in out
