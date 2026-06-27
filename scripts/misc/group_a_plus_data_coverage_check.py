#!/usr/bin/env python3
"""Compatibility entry point for the GroupA+ data coverage check."""

from group_a_plus.data.coverage import REQUIRED_TABLES, build_coverage, main


if __name__ == "__main__":
    main()
