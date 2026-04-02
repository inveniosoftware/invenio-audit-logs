..
    Copyright (C) 2025 CERN.
    Copyright (C) 2025-2026 Graz University of Technology.

    Invenio-Audit-Logs is free software; you can redistribute it and/or
    modify it under the terms of the MIT License; see LICENSE file for more
    details.

Changes
=======

Version v2.0.0 (released 2026-04-02)

- breaking change(mappings): define metadata as a flat_object instead of dynamic
- feat(config): Add config flag to disable actions as required
- refactor(results): Add global schema caching
- breaking change(schema): Add support for dynamic metadata schema validation per action

Version v1.1.0 (released 2026-03-16)

- fix(service): Return empty result when documents are not indexed yet
- feat(service): add action param to enable hidden filtering


Version v1.0.0 (released 2026-01-30)

- chore(setup): bump dependencies
- chore(black): update formatting to >= 26.0
- fix(chore): DeprecationWarning stdlib
- chore: replaced deprecated Link

Version v0.3.2 (released 2025-07-22)

- mappings: fix user search mappings

Version v0.3.1 (released 2025-07-14)

- chores: replaced importlib_xyz with importlib

Version 0.3.0 (released 2025-06-03)

- setup: bump major dependencies

Version 0.2.0 (released 2025-05-23)

- services: Add action builder
- mappings: rename user.name to user.username
- Refactor entrypoint registration using builder classes

Version 0.1.0 (released 2025-05-07)

- utility release

Version 1.0.0.dev1 (released 2025-05-06)

- add actions as registered entry points

Version 1.0.0.dev0 (released 2025-04-28)

- Initial dev release.
