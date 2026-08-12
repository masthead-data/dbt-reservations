import os
import yaml
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader, pass_context


class MockAdapter:
    def __init__(self, override_func=None):
        self.override_func = override_func

    @pass_context
    def dispatch(self, context, name, macro_namespace=None):
        if self.override_func:
            return self.override_func
        var_fn = context.get('var')
        def default_getter(project_name=None):
            return var_fn('RESERVATION_CONFIG', []) if var_fn else []
        return default_getter


def setup_env(cfg, model_obj, override_macro=None):
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)

    env.globals['adapter'] = MockAdapter(override_macro)
    env.globals['var'] = lambda key, default=None: cfg if key == 'RESERVATION_CONFIG' else default
    env.globals['model'] = model_obj
    env.globals['this'] = model_obj
    env.globals['return'] = lambda val: val
    env.globals['fromyaml'] = lambda s: yaml.safe_load(s)
    return env


def render_macro_with_cfg(cfg, model_obj, prefix=None, override_macro=None):
    env = setup_env(cfg, model_obj, override_macro)
    wrapper = """
{% from 'get_name_from_config.sql' import get_name_from_config, match_reservation_from_entries, get_bigquery_reservation_config, default__get_bigquery_reservation_config with context %}
{% from 'assign_from_config.sql' import assign_from_config with context %}
"""
    if prefix:
        wrapper += f"{{{{ assign_from_config(prefix='{prefix}') }}}}"
    else:
        wrapper += "{{ assign_from_config() }}"

    template = env.from_string(wrapper)
    return template.render()


def render_get_name_with_cfg(cfg, model_obj, override_macro=None):
    env = setup_env(cfg, model_obj, override_macro)
    wrapper = """
{% from 'get_name_from_config.sql' import get_name_from_config, match_reservation_from_entries, get_bigquery_reservation_config, default__get_bigquery_reservation_config with context %}
{{ get_name_from_config() }}
"""
    template = env.from_string(wrapper)
    res = template.render()
    if res is None or res.strip() == 'None':
        return ''
    return res


def test_matching_reservation():
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'projects/p/locations/l/reservations/r1' in out


def test_none_reservation():
    """Test that reservation: 'none' emits SET @@reservation= 'none' for on-demand pricing."""
    cfg = [
        {'tag': 'on_demand', 'reservation': 'none', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation= "none"' in out


def test_null_reservation():
    """Test that reservation: null (None in Python) results in no SET statement."""
    cfg = [
        {'tag': 'low_slots', 'reservation': None, 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation=' not in out


def test_no_matching_rule():
    """Test that a model not in any entry's models list results in no SET statement."""
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.other']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation=' not in out


def test_empty_models_list():
    """Test that an entry with empty models list doesn't match anything."""
    cfg = [
        {'tag': 'empty', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': []}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation=' not in out


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
    model_obj = SimpleNamespace(identifier='customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'projects/p/locations/l/reservations/r1' in out


def test_empty_config():
    """Test that an empty RESERVATION_CONFIG results in no SET statement."""
    cfg = []
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj)
    assert 'SET @@reservation=' not in out


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
    cfg = [
        {'tag': 'high', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_macro_with_cfg(cfg, model_obj, prefix='-- CUSTOM PREFIX:')
    assert '-- CUSTOM PREFIX: "projects/p/locations/l/reservations/r1"' in out


def test_get_name_matching_reservation():
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_get_name_with_cfg(cfg, model_obj)
    assert out.strip() == 'projects/p/locations/l/reservations/r1'


def test_get_name_none_reservation():
    cfg = [
        {'tag': 'on_demand', 'reservation': 'none', 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_get_name_with_cfg(cfg, model_obj)
    assert out.strip() == 'none'


def test_get_name_null_reservation():
    cfg = [
        {'tag': 'low_slots', 'reservation': None, 'models': ['model.test.customers']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_get_name_with_cfg(cfg, model_obj)
    assert out.strip() == ''


def test_get_name_no_matching_rule():
    cfg = [
        {'tag': 'high_slots', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['model.test.other']}
    ]
    model_obj = SimpleNamespace(unique_id='model.test.customers')
    out = render_get_name_with_cfg(cfg, model_obj)
    assert out.strip() == ''


def test_get_name_fallback_to_this_identifier():
    cfg = [
        {'tag': 'high', 'reservation': 'projects/p/locations/l/reservations/r1', 'models': ['customers']}
    ]
    model_obj = SimpleNamespace(identifier='customers')
    out = render_get_name_with_cfg(cfg, model_obj)
    assert out.strip() == 'projects/p/locations/l/reservations/r1'


def test_dispatched_config_override():
    """Test that when adapter.dispatch returns a configuration dictionary, get_name_from_config processes it."""
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)

    @pass_context
    def custom_config_macro(context, project_name=None, *args, **kwargs):
        all_cfg = {
            'analytics_project': [
                {'reservation': 'projects/overridden/locations/us/reservations/custom', 'models': ['model.test.any_model']}
            ]
        }
        return all_cfg.get(project_name) if project_name else all_cfg

    class MockAdapter:
        def dispatch(self, name, macro_namespace=None):
            return custom_config_macro

    env.globals['adapter'] = MockAdapter()
    env.globals['var'] = lambda key, default=None: default
    env.globals['project_name'] = 'analytics_project'
    env.globals['model'] = SimpleNamespace(unique_id='model.test.any_model', package_name='analytics_project')
    env.globals['this'] = SimpleNamespace(unique_id='model.test.any_model')
    env.globals['return'] = lambda val: val
    env.globals['fromyaml'] = lambda s: yaml.safe_load(s)

    wrapper = """
{% from 'get_name_from_config.sql' import get_name_from_config, match_reservation_from_entries, get_bigquery_reservation_config, default__get_bigquery_reservation_config with context %}
{% from 'assign_from_config.sql' import assign_from_config with context %}

{{ assign_from_config() }}
"""
    template = env.from_string(wrapper)
    out = template.render()
    assert 'SET @@reservation= "projects/overridden/locations/us/reservations/custom"' in out


def test_fallback_chain_central_dict_to_local_vars():
    """Test fallback chain when central dict has no match for a model, falling back to local project vars."""
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir), keep_trailing_newline=True)

    local_cfg = [
        {'tag': 'local', 'reservation': 'projects/p/locations/l/reservations/local_res', 'models': ['model.test.local_model']}
    ]

    @pass_context
    def platform_config_macro(context, project_name=None, *args, **kwargs):
        all_cfg = {
            'analytics_project': [
                {'reservation': 'projects/p/locations/l/reservations/central_res', 'models': ['model.test.central_model']}
            ]
        }
        return all_cfg.get(project_name) if project_name else all_cfg

    class MockAdapter:
        def dispatch(self, name, macro_namespace=None):
            return platform_config_macro

    env.globals['adapter'] = MockAdapter()
    env.globals['var'] = lambda key, default=None: local_cfg if key == 'RESERVATION_CONFIG' else default
    env.globals['project_name'] = 'analytics_project'
    env.globals['return'] = lambda val: val
    env.globals['fromyaml'] = lambda s: yaml.safe_load(s)

    wrapper = """
{% from 'get_name_from_config.sql' import get_name_from_config, match_reservation_from_entries, get_bigquery_reservation_config, default__get_bigquery_reservation_config with context %}
{% from 'assign_from_config.sql' import assign_from_config with context %}
{{ assign_from_config() }}
"""
    template = env.from_string(wrapper)

    # 1. Match in central config dict
    env.globals['model'] = SimpleNamespace(unique_id='model.test.central_model', package_name='analytics_project')
    env.globals['this'] = SimpleNamespace(unique_id='model.test.central_model')
    out1 = template.render()
    assert 'projects/p/locations/l/reservations/central_res' in out1

    # 2. Fall back to local project vars
    env.globals['model'] = SimpleNamespace(unique_id='model.test.local_model', package_name='analytics_project')
    env.globals['this'] = SimpleNamespace(unique_id='model.test.local_model')
    out2 = template.render()
    assert 'projects/p/locations/l/reservations/local_res' in out2
