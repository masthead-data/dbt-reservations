import os
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader


def render_macro_with_cfg(cfg, model_obj):
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)
    # wrapper to import macro and call it
    wrapper = """
{% from 'bq_reservation_from_config.sql' import bq_reservation_from_config %}
{{ bq_reservation_from_config() }}
"""
    template = env.from_string(wrapper)
    # pass the cfg via env.globals so var() will see it in dbt context simulation
    env.globals['var'] = lambda key, default=None: cfg if key == 'RESERVATION_CONFIG' else default
    env.globals['model'] = model_obj
    env.globals['this'] = model_obj
    return template.render()


def test_matching_reservation():
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'projects/p/locations/l/reservations/r1' in out


def test_none_reservation():
    cfg = [
        {'tag': 'on_demand', 'reservation': 'none', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'reservation explicitly none' in out


def test_null_reservation():
    """Test that reservation: null (None in Python) emits the explicitly none comment."""
    cfg = [
        {'tag': 'low_slots', 'reservation': None, 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'reservation explicitly none' in out


def test_no_matching_rule():
    """Test that a model not in any entry's models list gets the 'no matching' comment."""
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.other']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'no matching reservation rule for model.test.customers' in out


def test_empty_models_list():
    """Test that an entry with empty models list doesn't match anything."""
    cfg = [
        {'tag': 'empty', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': []}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'no matching reservation rule' in out


def test_first_match_wins():
    """Test that when multiple entries match, the first one is used."""
    cfg = [
        {'tag': 'first', 'reservation': 'projects/p/locations/l/reservations/first', 'models': ['model.test.customers']},
        {'tag': 'second', 'reservation': 'projects/p/locations/l/reservations/second', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'reservations/first' in out
    assert 'reservations/second' not in out


def test_fallback_to_this_identifier():
    """Test that when model.unique_id is not available, this.identifier is used."""
    cfg = [
        {'tag': 'high', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['customers']}
    ]
    # model_obj without unique_id attribute
    model_obj = SimpleNamespace(identifier='customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'projects/p/locations/l/reservations/r1' in out


def test_empty_config():
    """Test that an empty RESERVATION_CONFIG results in 'no matching' comment."""
    cfg = []
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'no matching reservation rule' in out


def test_set_statement_format():
    """Test that the SET statement is correctly formatted with quotes."""
    cfg = [
        {'tag': 'high', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation= "projects/p/locations/l/reservations/r1"' in out


def test_custom_prefix():
    """Test that a custom prefix can be passed to the macro."""
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)
    wrapper = """
{% from 'bq_reservation_from_config.sql' import bq_reservation_from_config %}
{{ bq_reservation_from_config(prefix='-- CUSTOM PREFIX:') }}
"""
    template = env.from_string(wrapper)
    cfg = [
        {'tag': 'high', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    env.globals['var'] = lambda key, default=None: cfg if key == 'RESERVATION_CONFIG' else default
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    env.globals['model'] = model_obj
    env.globals['this'] = model_obj
    out = template.render()
    assert '-- CUSTOM PREFIX: "projects/p/locations/l/reservations/r1"' in out
