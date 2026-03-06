"""Example usage of the profiler loader."""

from profilers.loader import ProfilerLoader
from profilers.profiler import Profilers


def main():
    """Demonstrate profiler loading and dependency resolution."""
    # Create a Profilers instance
    profiler = Profilers()

    # Load configuration into the instance
    ProfilerLoader.load(profiler)

    # Example 1: Nice print using str()
    print(profiler)

    print("\n" + "=" * 60)

    # Example 2: Access nvidia profiler (includes all transitive dependencies)
    profiler_name = "nvidia"
    print(f"\nProfiler '{profiler_name}' includes (flat):")
    print(f"  {sorted(profiler[profiler_name])}")
    print("\nThis includes 'ai' and all its dependencies: 'ai-base', 'gpu', 'general'")

    print("\n" + "=" * 60)

    # Example 3: all includes everything
    profiler_name = "all"
    print(f"\nProfiler '{profiler_name}' includes (flat):")
    print(f"  {sorted(profiler[profiler_name])}")

    print("\n" + "=" * 60)

    # Example 4: Test error handling with helpful message
    print("\nTesting error handling for non-existent profiler:")
    print("Trying to access profiler['does_not_exist']...\n")
    try:
        profiler["does_not_exist"]
    except KeyError as e:
        print(f"KeyError caught with helpful message:\n{e}")

    print("\n" + "=" * 60)

    # Example 5: Using repr()
    print(f"\nUsing repr(): {repr(profiler)}")

    print("\n" + "=" * 60)
    print("\nNotes:")
    print("- Create a Profilers() instance and pass it to ProfilerLoader.load()")
    print("- Dependencies are resolved at load time into flat sets")
    print("- Circular dependencies are detected and raise ValueError")
    print("- Use str(profiler) or print(profiler) for nice formatting")
    print("- Accessing non-existent profilers shows all available options")


if __name__ == "__main__":
    main()
