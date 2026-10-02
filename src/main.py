from src.factories import EnvironmentFactory, PopulationConfig, RegionConfig


def main() -> None:
    environment = EnvironmentFactory.create(
        PopulationConfig(
            regions=(
                RegionConfig(name="Coast", households=10, homes=12),
                RegionConfig(name="Inland", households=20, homes=18),
            ),
            seed=42,
        )
    )
    print(
        f"Created {len(environment.regions)} regions, {len(environment.people)} people, "
        f"{len(environment.households)} households, and {len(environment.homes)} homes."
    )
    for _ in range(3):
        result = environment.step()
        paid = sum(action.paid is True for action in result.actions)
        missed = sum(action.paid is False for action in result.actions)
        print(f"Period {result.period}: {paid} rent payments, {missed} missed payments.")


if __name__ == "__main__":
    main()
