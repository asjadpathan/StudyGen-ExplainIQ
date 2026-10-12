# Contributing to Explain IQ

Thank you for your interest in contributing to Explain IQ! We welcome contributions, bug fixes, feature requests, and documentation enhancements.

## Code of Conduct

Please help us maintain a welcoming, respectful, and inclusive community. Be constructive in discussions and considerate of fellow contributors.

## How to Contribute

### 1. Reporting Issues
- Check the issue tracker before submitting a new bug report to avoid duplicates.
- Provide a clear title, reproducible steps, your Python/environment version, and relevant logs or error stack traces.

### 2. Proposing Features
- Open an issue tagged with `feature-request` outlining the use case, proposed API changes, and implementation considerations.

### 3. Submitting Pull Requests

1. **Fork the Repository** and create a descriptive branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Set Up the Development Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. **Make Your Changes**:
   - Adhere to PEP 8 styling conventions for Python code.
   - Maintain existing docstrings, type annotations, and logging standards.
   - Ensure changes do not introduce blocking synchronous calls into asynchronous worker paths.
4. **Test Thoroughly**:
   - Verify that FastAPI endpoints return expected HTTP status codes and schemas.
   - Run pipeline rendering tests with `duration_mode="quick"` to validate visual and audio synthesis.
5. **Commit and Push**:
   - Use conventional commit messages (e.g., `feat: add font fallback resolution`, `fix: handle edge-tts timeout`).
   ```bash
   git commit -m "feat: description of changes"
   git push origin feature/your-feature-name
   ```
6. **Open a Pull Request**:
   - Provide a clear summary of your changes and reference any related issues.

## Development Guidelines

- **Zero Heavy Renderers**: Keep slide and visual generation lightweight (rely on native Pillow and NumPy instead of heavyweight C/C++ or external software renderers like LaTeX/Blender).
- **Graceful Fallbacks**: Ensure stock photo fetching and external API calls fail over cleanly without terminating worker pipelines.
- **Resource Cleanup**: Always use temp file cleanup patterns and isolated per-job directories inside `tmp/`.

## Questions or Support

If you have questions, feel free to open a GitHub Discussion or submit an issue.
