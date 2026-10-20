# Profiles

A profile is a Python policy for deciding which tracks go into an output and how the result is
checked. VideoForge supplies the discovery, probing, encoding, muxing, and queue engine.

The built-in **manual** profile keeps tracks in source order and lets the user exclude, reorder,
retitle, flag, and encode them. A release group can install its own profile as a separate package.

## Register a package

Declare a `videoforge.profiles` entry point in the profile package's `pyproject.toml`:

```toml
[project.entry-points."videoforge.profiles"]
my_profile = "my_profile.profile:MyProfile"
```

Install that package into the Python environment running VideoForge. Select its ID in **Settings**
or set the top-level configuration key:

```toml
profile = "my_profile"
```

## Implement the policy

Subclass `videoforge.core.profile.Profile`. The required `plan(probed, original_language, overrides)`
method returns a `Plan`: selected audio and subtitle tracks, actions, titles, flags, chapters,
and issues. Missing information that would require guessing should produce a blocking issue.

| Hook or field | Purpose |
| --- | --- |
| `id`, `name`, `container`, `containers` | Profile identity and supported output containers |
| `plan(...)` | Turn probed inputs and user overrides into a track plan |
| `video_defaults()`, `audio_settings()` | Default processing and encoder configuration |
| `validate_output(plan, output)` | Check a completed job against its plan; a blocking issue makes it invalid |
| `validate_release(info)` | Check an arbitrary release through the CLI `validate` command |

`track_editor`, `track_properties`, `external_subtitles`, and `external_audio` control which editing
and external-track features are available. `output_stem(plan)` controls the base output name.

Use the current
[Profile interface](https://github.com/jessielw/VideoForge/blob/main/src/videoforge/core/profile.py)
and [manual implementation](https://github.com/jessielw/VideoForge/blob/main/src/videoforge/profiles/manual.py)
as the concrete reference. Profiles use the core Python types and should be checked when updating
VideoForge; they do not have the separately versioned plugin API.

## Profiles, templates, and plugins

A template saves user settings without a source. A profile defines planning and validation policy.
A plugin responds to lifecycle events after the queue emits them. Choose the smallest extension
point that expresses the behavior you need.
