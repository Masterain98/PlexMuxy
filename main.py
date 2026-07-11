import warnings

from plexmuxy.cli import main


if __name__ == "__main__":
    warnings.warn(
        "This entry point is deprecated; use `plexmuxy` or `python -m plexmuxy`.",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
