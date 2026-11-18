import unittest

import robust_examples


def main() -> int:
    suite = unittest.defaultTestLoader.discover(start_dir="tests", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    # The baseline V1 and robust examples are separate executable checks.
    robust_examples.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
