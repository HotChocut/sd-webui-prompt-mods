import html, importlib, json, re
import gradio as gr
from modules import script_callbacks, scripts, shared
from modules.ui_components import InputAccordion

TITLE = "Prompt Mods"
SECTION = ("promptmods", TITLE)
INFO = (
    ("enabled", False, "prompt_mods_default_enabled", "Prompt Mods enabled"),
    ("pos_before", "", "prompt_mods_default_positive_before", "Prompt Mods positive before"),
    ("pos_after", "", "prompt_mods_default_positive_after", "Prompt Mods positive after"),
    ("neg_before", "", "prompt_mods_default_negative_before", "Prompt Mods negative before"),
    ("neg_after", "", "prompt_mods_default_negative_after", "Prompt Mods negative after"),
    ("use_pos", True, "prompt_mods_default_apply_positive", "Prompt Mods use positive"),
    ("use_neg", True, "prompt_mods_default_apply_negative", "Prompt Mods use negative"),
    ("strip", True, "prompt_mods_strip_infotext_imports", None),
)
FIELDS = tuple(x[0] for x in INFO[:7])
DEFAULTS = {k: v for k, v, _, _ in INFO}
OPTS = {k: v for k, _, v, _ in INFO}
PARAMS = {k: v for k, _, _, v in INFO if v}
BOOLS = {"enabled", "use_pos", "use_neg", "strip"}
PROMPTS = (
    ("use_pos", "pos_before", "pos_after", "Prompt", "prompt", "all_prompts", "main_prompt", "all_hr_prompts"),
    ("use_neg", "neg_before", "neg_after", "Negative prompt", "negative_prompt", "all_negative_prompts", "main_negative_prompt", "all_hr_negative_prompts"),
)
SETTINGS = (
    ("enabled", "Enable by default", None, None, True),
    ("pos_before", "Default text before positive prompt", gr.Textbox, {"lines": 2}, True),
    ("pos_after", "Default text after positive prompt", gr.Textbox, {"lines": 2}, True),
    ("neg_before", "Default text before negative prompt", gr.Textbox, {"lines": 2}, True),
    ("neg_after", "Default text after negative prompt", gr.Textbox, {"lines": 2}, True),
    ("use_pos", "Change positive prompt by default", None, None, True),
    ("use_neg", "Change negative prompt by default", None, None, True),
    ("strip", "Remove Prompt Mods text on PNG Info / Image Browser import", None, None, False),
)
TRUE = {"1", "true", "yes", "on", "enabled", "enable"}
FALSE = {"0", "false", "no", "off", "disabled", "disable", "none", ""}
START_SEP_RE = re.compile(r"^(?:\s+|[,;:.]\s*)+")
END_SEP_RE = re.compile(r"(?:\s+|[,;:.]\s*)+$")
PARAM_RE = re.compile(r'\s*(\w[\w \-/]+):\s*("(?:\\.|[^\\"])+"|[^,]*)(?:,|$)')
VAR_RE = re.compile(r"\{([^{}]*\|[^{}]*)\}")
RAW_PATCHED = "__prompt_mods_raw_patched__"
ORIGINAL_SETUP = "__prompt_mods_original_setup__"
STATE_ATTR = "_prompt_mods_state"
APPLIED_ATTR = "_prompt_mods_applied"
STRIPPED = "__prompt_mods_stripped__"

def clean(value):
    return str(value or "").strip()
def as_bool(value, default=False):
    if isinstance(value, bool): return value
    if value is None: return default
    if isinstance(value, (int, float)): return bool(value)
    value = str(value).strip().lower()
    return True if value in TRUE else False if value in FALSE else default
def opt(key):
    opts = getattr(shared, "opts", None)
    data = getattr(opts, "data", {})
    value = data.get(OPTS[key], getattr(opts, OPTS[key], DEFAULTS[key])) if isinstance(data, dict) else getattr(opts, OPTS[key], DEFAULTS[key])
    return as_bool(value, DEFAULTS[key]) if key in BOOLS else clean(value)
def state(*values):
    values = list(values) + [DEFAULTS[k] for k in FIELDS[len(values):]]
    return {k: as_bool(v, DEFAULTS[k]) if k in BOOLS else clean(v) for k, v in zip(FIELDS, values)}
def default_state():
    return state(*(opt(k) for k in FIELDS))
def metadata_state(params):
    result = state(True, *(params.get(PARAMS[k]) for k in FIELDS[1:]))
    return result if active(result) else None
def active(s):
    return s and s["enabled"] and ((s["use_pos"] and (s["pos_before"] or s["pos_after"])) or (s["use_neg"] and (s["neg_before"] or s["neg_after"])))

def gap_before(before):
    return "" if before[-1:].isspace() else " " if before.rstrip().endswith((",", ";", ":", ".")) else ", "
def gap_after(prompt, after):
    return "" if prompt[-1:].isspace() or after.startswith((",", ";", ":", ".")) else ", "
def strip_before(prompt, before):
    prompt, before = "" if prompt is None else str(prompt), clean(before)
    if not before: return prompt
    lead = prompt[:len(prompt) - len(prompt.lstrip())]
    body = prompt[len(lead):]
    if not body.startswith(before): return prompt
    rest = body[len(before):]
    if not rest: return lead
    match = START_SEP_RE.match(rest)
    return lead + rest[match.end():].lstrip() if match else prompt
def strip_after(prompt, after):
    prompt, after = "" if prompt is None else str(prompt), clean(after)
    if not after: return prompt
    trail = prompt[len(prompt.rstrip()):]
    body = prompt[:len(prompt) - len(trail)]
    if not body.endswith(after): return prompt
    rest = body[:-len(after)]
    match = END_SEP_RE.search(rest)
    if match: return rest[:match.start()].rstrip() + trail
    return rest + trail if not rest or after.startswith((",", ";", ":", ".")) else prompt

def variants(value, limit=128):
    values = [clean(value)]
    for _ in range(20):
        changed, expanded = False, []
        for value in values:
            match = VAR_RE.search(value)
            if not match:
                expanded.append(value); continue
            changed = True
            for part in match.group(1).split("|"):
                weighted = re.match(r"^\s*[-+]?\d+(?:\.\d+)?::(.*)$", part, re.S)
                expanded.append(value[:match.start()] + clean(weighted.group(1) if weighted else part) + value[match.end():])
                if len(expanded) >= limit: return list(dict.fromkeys(x for x in expanded if x))
        values = expanded
        if not changed: break
    return list(dict.fromkeys(x for x in values if x))
def strip_many(prompt, values, fn):
    prompt = "" if prompt is None else str(prompt)
    values = sorted({item for value in values for item in variants(value)}, key=len, reverse=True)
    for _ in range(10):
        old = prompt
        for value in values:
            prompt = fn(prompt, value)
            if prompt != old: break
        if prompt == old: break
    return prompt
def add_before(value, prompt):
    if isinstance(prompt, list): return [add_before(value, item) for item in prompt]
    value, prompt = clean(value), "" if prompt is None else str(prompt)
    if not value or strip_before(prompt, value) != prompt: return prompt
    return value if not prompt.strip() else value + gap_before(value) + prompt.lstrip()
def add_after(value, prompt):
    if isinstance(prompt, list): return [add_after(value, item) for item in prompt]
    value, prompt = clean(value), "" if prompt is None else str(prompt)
    if not value or strip_after(prompt, value) != prompt: return prompt
    prompt = prompt.rstrip()
    return value if not prompt else prompt + gap_after(prompt, value) + value
def apply_text(prompt, before, after):
    return add_after(after, add_before(before, prompt))

def sync(p, attr, all_attr, main_attr):
    values = getattr(p, all_attr, None)
    if values:
        setattr(p, main_attr, values[0])
        setattr(p, attr, values if isinstance(getattr(p, attr, None), list) else values[0])
def apply_mods(p, s, hr_pos=False, hr_neg=False):
    if not active(s): return False
    for use, before, after, _param, attr, all_attr, main_attr, hr_all_attr in PROMPTS:
        if not s[use]: continue
        before, after = s[before], s[after]
        if getattr(p, all_attr, None) is not None:
            setattr(p, all_attr, apply_text(getattr(p, all_attr), before, after)); sync(p, attr, all_attr, main_attr)
        elif hasattr(p, attr):
            setattr(p, attr, apply_text(getattr(p, attr), before, after))
        if ((use == "use_pos" and hr_pos) or (use == "use_neg" and hr_neg)) and getattr(p, hr_all_attr, None) is not None:
            setattr(p, hr_all_attr, apply_text(getattr(p, hr_all_attr), before, after))
    return True
def record(p, s):
    if not active(s): return
    if getattr(p, "extra_generation_params", None) is None: p.extra_generation_params = {}
    for key in FIELDS:
        if key in BOOLS or s[key]: p.extra_generation_params[PARAMS[key]] = s[key]
def script_state(p):
    if getattr(p, STATE_ATTR, None) is not None: return getattr(p, STATE_ATTR)
    args, runner = getattr(p, "script_args", None), getattr(p, "scripts", None)
    for script in list(getattr(runner, "alwayson_scripts", []) or []) + list(getattr(runner, "scripts", []) or []):
        if script.__class__.__module__ != __name__: continue
        start, end = getattr(script, "args_from", None), getattr(script, "args_to", None)
        if start is not None and end is not None and len(args or ()) >= end: return state(*list(args[start:end])[:len(FIELDS)])
    return default_state()
def apply_now(p, hr_pos=False, hr_neg=False):
    if getattr(p, APPLIED_ATTR, False): return
    s = script_state(p)
    if apply_mods(p, s, hr_pos, hr_neg):
        setattr(p, APPLIED_ATTR, True); record(p, s)

def strip_params(params):
    s = metadata_state(params) or default_state()
    if not s: return
    for use, before, after, param, *_ in PROMPTS:
        if s[use] and param in params:
            params[param] = strip_many(strip_many(params[param], [s[before]], strip_before), [s[after]], strip_after)
def strip_mods_from_params(_infotext, params):
    if isinstance(params, dict) and not params.get(STRIPPED) and opt("strip"):
        strip_params(params); params[STRIPPED] = True

def unquote(value):
    if len(value) > 1 and value[0] == value[-1] == '"':
        try: return json.loads(value)
        except Exception: return value[1:-1]
    return value
def quote(value):
    value = str(value)
    return json.dumps(value, ensure_ascii=False) if any(x in value for x in (",", "\n", ":")) else value
def split_infotext(raw):
    raw = "" if raw is None else str(raw).strip()
    if not raw: return {}, False
    *lines, last = raw.split("\n")
    if len(PARAM_RE.findall(last)) < 3:
        lines.append(last); last = ""
    params = {key: unquote(value) for key, value in PARAM_RE.findall(last)}
    positive, negative, is_negative = [], [], False
    for line in lines:
        line = line.strip()
        if line.startswith("Negative prompt:"):
            is_negative, line = True, line[16:].strip()
        (negative if is_negative else positive).append(line)
    params["Prompt"] = "\n".join(positive)
    params["Negative prompt"] = "\n".join(negative)
    return params, bool(last)
def join_infotext(params, has_params):
    params = dict(params)
    prompt, negative = params.pop("Prompt", ""), params.pop("Negative prompt", "")
    lines = str(prompt).split("\n") if prompt else []
    if negative:
        neg_lines = str(negative).split("\n")
        lines += ["Negative prompt: " + neg_lines[0]] + neg_lines[1:]
    if has_params and params: lines.append(", ".join(f"{key}: {quote(value)}" for key, value in params.items()))
    return "\n".join(lines)
def clean_raw_infotext(raw):
    if not opt("strip"): return raw
    params, has_params = split_infotext(raw)
    if not params: return raw
    old = dict(params); strip_params(params)
    return raw if params == old else join_infotext(params, has_params)

def metadata_update(params, field):
    s = metadata_state(params)
    value = None if s is None else s[field]
    return gr.update(value=value) if value not in (None, "") else gr.update()
def add_option(key, label, component=None, args=None, reload=False):
    info = shared.OptionInfo(opt(key), label, component, args, section=SECTION)
    info.section = SECTION; info.category_id = None
    if reload and hasattr(info, "needs_reload_ui"): info.needs_reload_ui()
    shared.opts.add_option(OPTS[key], info)
def on_ui_settings():
    for setting in SETTINGS: add_option(*setting)

def patch_parser():
    for name in ("modules.infotext_utils", "modules.generation_parameters_copypaste"):
        try:
            module = importlib.import_module(name)
            original = getattr(module, "parse_generation_parameters", None)
        except Exception:
            continue
        if original is None or getattr(original, RAW_PATCHED, False): continue
        def wrapped(value, *args, __original=original, **kwargs):
            return __original(clean_raw_infotext(value), *args, **kwargs)
        setattr(wrapped, RAW_PATCHED, True)
        module.parse_generation_parameters = wrapped
def patch_setup_prompts():
    try: processing = importlib.import_module("modules.processing")
    except Exception: return
    def patch(cls, skip_txt2img=False):
        if cls is None or not hasattr(cls, "setup_prompts"): return
        original = getattr(cls.setup_prompts, ORIGINAL_SETUP, cls.setup_prompts)
        def wrapped(self, *args, __original=original, __skip_txt2img=skip_txt2img, **kwargs):
            hr_pos = as_bool(getattr(self, "enable_hr", False)) and not clean(getattr(self, "hr_prompt", ""))
            hr_neg = as_bool(getattr(self, "enable_hr", False)) and not clean(getattr(self, "hr_negative_prompt", ""))
            result = __original(self, *args, **kwargs)
            if not (__skip_txt2img and self.__class__.__name__ == "StableDiffusionProcessingTxt2Img"): apply_now(self, hr_pos, hr_neg)
            return result
        setattr(wrapped, ORIGINAL_SETUP, original)
        cls.setup_prompts = wrapped
    patch(getattr(processing, "StableDiffusionProcessing", None), True)
    patch(getattr(processing, "StableDiffusionProcessingTxt2Img", None))

def no_config(*controls):
    for control in controls:
        for target in (control, getattr(control, "accordion", None)):
            try: target.do_not_save_to_config = True
            except Exception: pass

class Script(scripts.Script):
    section = None
    create_group = False
    def title(self): return TITLE
    def show(self, is_img2img): return scripts.AlwaysVisible
    def ui(self, is_img2img):
        accordion_id = self.elem_id("accordion")
        with gr.Group(elem_id=self.elem_id("group")) as group:
            with InputAccordion(False, label=TITLE, elem_id=accordion_id) as enabled:
                marker = gr.HTML(f'<div class="prompt-mods-default-enabled" data-accordion-id="{html.escape(accordion_id, quote=True)}" data-enabled="{str(opt("enabled")).lower()}" style="display:none"></div>', elem_id=self.elem_id("default_enabled_marker"))
                with gr.Accordion("Text added before prompt", open=False, elem_id=self.elem_id("before_group")) as before_group:
                    pos_before = gr.Textbox(label="Positive prompt", lines=2, value=opt("pos_before"), placeholder="Example: masterpiece, best quality", elem_id=self.elem_id("positive_before"))
                    neg_before = gr.Textbox(label="Negative prompt", lines=2, value=opt("neg_before"), placeholder="Example: worst quality, low quality", elem_id=self.elem_id("negative_before"))
                with gr.Accordion("Text added after prompt", open=False, elem_id=self.elem_id("after_group")) as after_group:
                    pos_after = gr.Textbox(label="Positive prompt", lines=2, value=opt("pos_after"), placeholder="Example: cinematic lighting, detailed background", elem_id=self.elem_id("positive_after"))
                    neg_after = gr.Textbox(label="Negative prompt", lines=2, value=opt("neg_after"), placeholder="Example: blurry, artifacts", elem_id=self.elem_id("negative_after"))
                with gr.Row():
                    use_pos = gr.Checkbox(value=opt("use_pos"), label="Change positive prompt", elem_id=self.elem_id("use_positive"))
                    use_neg = gr.Checkbox(value=opt("use_neg"), label="Change negative prompt", elem_id=self.elem_id("use_negative"))
        controls = [enabled, pos_before, pos_after, neg_before, neg_after, use_pos, use_neg]
        no_config(group, marker, before_group, after_group, *controls)
        self.infotext_fields = [(control, lambda params, field=field: metadata_update(params, field)) for control, field in zip(controls, FIELDS)]
        self.paste_field_names = list(PARAMS.values())
        return controls
    def setup(self, p, *values):
        setattr(p, STATE_ATTR, state(*values[:len(FIELDS)]))
    def process(self, p, *values):
        if not getattr(p, APPLIED_ATTR, False):
            setattr(p, STATE_ATTR, state(*values[:len(FIELDS)])); apply_now(p, True, True)

script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_infotext_pasted(strip_mods_from_params)
patch_parser()
patch_setup_prompts()
