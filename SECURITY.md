# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting feature when enabled, or contact the repository owner
privately through their GitHub profile. Include affected files, impact,
reproduction steps, and a minimal proof of concept.

Maintainers will acknowledge a complete report, assess impact, coordinate a fix,
and publish an advisory when appropriate. No fixed response-time SLA is promised.

## Security boundaries

CoordProof processes complex IFC, STEP, STL, DXF, PDF, FCStd, and script inputs.
Treat files from untrusted sources as potentially hostile:

- run imports and desktop CAD applications in an isolated environment;
- do not execute contributed Python, FreeCAD macros, OpenSCAD, or OpenCAD agent
  output without review;
- apply CPU, memory, file-size, and execution-time limits in hosted services;
- never expose FreeCAD, QCAD, OpenSCAD, or the optional OpenCAD service directly
  to the internet;
- keep API keys and project/client data outside the repository.

The example mechanical-room package is synthetic and contains no customer data.
