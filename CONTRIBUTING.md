# X-AnyLabeling - Contributing Guide 🌟

We're thrilled that you want to contribute to X-AnyLabeling, the future of communication! 😄

X-AnyLabeling is an open-source project, and we welcome your collaboration. Before you jump in, let's make sure you're all set to contribute effectively and have loads of fun along the way!

## Table of Contents

- [Fork the Repository](#fork-the-repository)
- [Clone Your Fork](#clone-your-fork)
- [Create a New Branch](#create-a-new-branch)
- [Testing Conventions (This Fork)](#testing-conventions-this-fork)
- [Code Like a Wizard](#code-like-a-wizard)
- [Committing Your Work](#committing-your-work)
- [Sync with Upstream](#sync-with-upstream)
- [Open a Pull Request](#open-a-pull-request)
- [Review and Collaboration](#review-and-collaboration)
- [Celebrate 🎉](#celebrate-)

## Fork the Repository

🍴 Fork this repository to your GitHub account by clicking the "Fork" button at the top right. This creates a personal copy of the project you can work on.

## Clone Your Fork

📦 Clone your forked repository to your local machine using the `git clone` command:

```bash
git clone https://github.com/YourUsername/X-AnyLabeling.git
```

## Create a New Branch

🌿 Create a new branch for your contribution. This helps keep your work organized and separate from the main codebase.

```bash
git checkout -b your-branch-name
```

Choose a meaningful branch name related to your work. It makes collaboration easier!

## Google-Style Docstrings

For clarity and maintainability, any new functions or classes must include [Google-style docstrings](https://google.github.io/styleguide/pyguide.html) and use Python type hints. Type hints are mandatory in all function definitions, ensuring explicit parameter and return type declarations. These docstrings should clearly explain parameters, return types, and provide usage examples when applicable.

For example:

```python
def greet(name: str, greeting: str = "Hello") -> str:
    """
    Greets a person with a specified greeting.

    Args:
        name (str): The name of the person to greet.
        greeting (str): The greeting message to use, defaults to "Hello".

    Returns:
        str: A greeting message.

    Examples:
        >>> greet("World")
        'Hello, World!'
        >>> greet("CVHub", "Hi")
        'Hi, CVHub!'
    """
    return f"{greeting}, {name}!"
```

Following this pattern helps ensure consistency throughout the codebase.

## Testing Conventions (This Fork)

This section is how the test suite actually works here. It was learned the
hard way — read it before writing or changing tests, and before adding a
method call to existing widget code.

### The `SimpleNamespace` stub pattern

Most unit tests in `tests/` do not boot Qt. They call **real methods on fake
widgets**:

```python
from types import SimpleNamespace
from anylabeling.views.labeling.label_widget import LabelingWidget

widget = SimpleNamespace(canvas=SimpleNamespace(), actions=SimpleNamespace())
result = LabelingWidget.apply_attribute_change(widget, shape, "label", "cat")
```

The stub carries only the members the code path under test actually touches.
This keeps logic tests fast, deterministic and Qt-free — but it creates one
sharp edge:

### New `self.foo()` calls break old stubs

A `SimpleNamespace` stub has **no class hierarchy**: if you add a call to a
new (or existing) instance method inside a method the stubs already traverse,
every such test fails with `AttributeError: 'SimpleNamespace' object has no
attribute 'foo'` — even though the application itself is fine. This has
bitten real refactors: a batch that made settings code touch
`QCoreApplication`-related attributes directly turned 17 passing tests red
in one commit, purely because the stubs could not serve the new members.

**The rule that prevents it: put new helper logic in module-level functions
that take the widget as the first argument, not in new class methods.**

```python
# In some_module.py next to the widget:
def apply_attribute_change(widget, shape, key, value):
    ...  # uses widget.canvas, widget.actions, ...

# label_widget.py keeps a thin delegate so existing call sites still work:
def apply_attribute_change(self, shape, key, value):
    return some_module.apply_attribute_change(self, shape, key, value)
```

Stubs can reach module-level functions (the test imports and calls them
directly, or the thin delegate runs against the stub's members), so old
stubs survive the refactor untouched. This is exactly how
`attributes_controller.py`, `settings/appearance.py` and the canvas mixins
already work — follow those precedents.

### When you must extend a stub

If a code path genuinely needs a new member on a stub, add **exactly what
that path touches** — `widget.canvas.store_shapes`, `widget.actions.undo`,
a `MagicMock` for a collaborator — and nothing speculative. If you find
yourself adding more than a handful of members, that is a signal the logic
belongs in a module-level function instead.

### Two related invariants

- **Tests must never write the real user config.** Anything that saves
  config must run under `config.set_work_directory(tmp_path)` with a
  `finally` that restores the old work directory — `save_config` falls
  through to `~/.xanylabelingrc` when the current config file does not
  exist yet, and a test that forgets this corrupts a real user file.
- **Wiring claims get real objects.** Stub tests verify logic;
  `tests/test_labeling/test_widget_wiring.py` constructs the real
  `LabelingWidget` and is the place for "this shortcut exists", "this
  action is enabled when..." style assertions. Do not weaken the real
  fixture to make a stub test pass — fix the stub or the code.

Run the full suite before committing: `python -m pytest tests -q`.
CI runs the same thing, but a red commit wastes a round trip for everyone.

## Code Like a Wizard

🧙‍♀️ Time to work your magic! Write your code, fix bugs, or add new features. Be sure to follow our project's coding style. You can check if your code adheres to our style using:

```bash
bash scripts/format_code.sh
```

This adds a bit of enchantment to your coding experience! ✨

## Committing Your Work

📝 Ready to save your progress? Commit your changes to your branch.

```bash
git add .
git commit -m "Your meaningful commit message"
```

Please keep your commits focused and clear. And remember to be kind to your fellow contributors; keep your commits concise.

## Sync with Upstream

⚙️ Periodically, sync your forked repository with the original (upstream) repository to stay up-to-date with the latest changes.

```bash
git remote add upstream https://github.com/CVHub520/X-AnyLabeling.git
git fetch upstream
git merge upstream/main
```

This ensures you're working on the most current version of X-AnyLabeling. Stay fresh! 💨

## Open a Pull Request

🚀 Time to share your contribution! Head over to the original X-AnyLabeling repository and open a Pull Request (PR). Our maintainers will review your work.

## Review and Collaboration

👓 Your PR will undergo thorough review and testing. The maintainers will provide feedback, and you can collaborate to make your contribution even better. We value teamwork!

## Celebrate 🎉

🎈 Congratulations! Your contribution is now part of X-AnyLabeling. 🥳

Thank you for making X-AnyLabeling even more magical. We can't wait to see what you create! 🌠

Happy Coding! 🚀🦄