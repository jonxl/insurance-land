"""Generate a Standard-world report: uv run python -m experiments.standard_report."""

import argparse
import csv
import json
import platform
from dataclasses import asdict
from decimal import Decimal
from math import exp, factorial
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from cycler import cycler
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, to_hex

from experiments.recording import WorldRecorder
from experiments.standard import StandardWorld
from factories import GridPopulationFactory
from utils.distributions import numpy_stream, price_field, sample_disasters, smooth_field

# Palette from plans/active/figures/generate_distribution_figures.py.
BLUE, ORANGE, PURPLE = "#245b91", "#ba5a22", "#6a51a3"
VARIANCE_COLORS = LinearSegmentedColormap.from_list("report_variance", [BLUE, "#ffffff", ORANGE])


def generate(output: Path, spec: StandardWorld, draws: int) -> dict[str, object]:
    if draws < 1000:
        raise ValueError("Use at least 1000 diagnostic draws")
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "axes.prop_cycle": cycler(color=[BLUE, ORANGE, PURPLE]),
        }
    )
    figures: list[tuple[str, str]] = []

    def save(name: str, caption: str) -> None:
        plt.gcf().tight_layout()
        plt.savefig(assets / f"{name}.png")
        plt.savefig(assets / f"{name}.pdf")
        plt.close()
        figures.append((name, caption))

    scenario = GridPopulationFactory.create(spec.population())
    world = spec.create()
    shape = (spec.rows, spec.columns)
    prices = np.array([float(h.market_value) for h in scenario.homes]).reshape(shape)
    incomes = np.array([float(p.annual_income or Decimal(0)) for p in scenario.people])
    counts = np.bincount([h.owner_id - 1 for h in scenario.homes], minlength=len(incomes))
    residents = np.array([(h.occupant_id or 0) - 1 for h in scenario.homes]).reshape(shape)
    owners = np.array([h.owner_id for h in scenario.homes]).reshape(shape)
    owner_ids = np.unique(owners)
    # Categorical colors: labels identify owners even when shades look similar.
    colors = plt.get_cmap("Set3")(np.arange(len(owner_ids)) % 12)
    ownership_cmap = ListedColormap(colors)
    owner_indices = np.searchsorted(owner_ids, owners)
    probabilities = spec.disasters().risk_probabilities(shape, seed=spec.seed)
    exposure = np.zeros(shape)
    for a in range(probabilities.shape[0]):
        for b in range(probabilities.shape[1]):
            exposure[a : a + 3, b : b + 3] += probabilities[a, b]
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, data, title, cmap in zip(
        axes.flat,
        [
            prices / 1000,
            incomes[residents] / 1000,
            owner_indices,
            100 * (1 - np.exp(-spec.rate * exposure)),
        ],
        [
            "Initial home price ($ thousands)",
            "Resident annual income ($ thousands)",
            "Ownership map (labels = owner IDs)",
            "Disaster exposure per period (%)",
        ],
        ["YlOrBr", "YlOrBr", "Blues", "Purples"],
        strict=True,
    ):
        is_ownership = ax is axes[1, 0]
        im = ax.imshow(
            data,
            origin="upper",
            cmap=ownership_cmap if is_ownership else cmap,
            vmin=-0.5 if is_ownership else None,
            vmax=len(owner_ids) - 0.5 if is_ownership else None,
            interpolation="nearest",
        )
        ax.set_xticks(np.arange(-0.5, data.shape[1]), minor=True)
        ax.set_yticks(np.arange(-0.5, data.shape[0]), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.4)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set(title=title, xlabel="Column", ylabel="Row")
        if is_ownership:
            for (row, column), owner in np.ndenumerate(owners):
                ax.text(column, row, str(owner), ha="center", va="center", fontsize=5)
        else:
            fig.colorbar(im, ax=ax, shrink=0.75)
    save(
        "01-world",
        "Researcher view of the initialized world. Risk is hidden from agents. "
        "Ownership labels identify people, not wealth. Colors are categorical and reused; "
        "use the labeled ownership map and owner key below to trace a person's homes. "
        "The purple map gives each home’s percentage chance of at least one disaster hit "
        "during a period. Darker means greater exposure.",
    )

    fig, ax = plt.subplots(figsize=(11, 11))
    ax.imshow(owner_indices, cmap=ownership_cmap, vmin=-0.5, vmax=len(owner_ids) - 0.5)
    for (row, column), owner in np.ndenumerate(owners):
        ax.text(column, row, str(owner), ha="center", va="center", fontsize=9)
    ax.set_xticks(np.arange(-0.5, spec.columns), minor=True)
    ax.set_yticks(np.arange(-0.5, spec.rows), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set(
        title="Who owns each home?\nEach cell label is an owner ID", xlabel="Column", ylabel="Row"
    )
    save(
        "01-ownership",
        "Each square is a home. Repeated IDs identify the same owner, "
        "including disconnected properties. Colors do not encode a quantity. "
        '<a href="ownership.html">Open the selectable owner key and map</a>.',
    )

    cells = []
    for (row, column), owner in np.ndenumerate(owners):
        color = to_hex(colors[int(np.searchsorted(owner_ids, owner))])
        cells.append(
            f'<g data-owner="{owner}"><rect x="{column * 40}" y="{row * 40}" '
            f'width="40" height="40" fill="{color}" stroke="white"/>'
            f'<text x="{column * 40 + 20}" y="{row * 40 + 24}" text-anchor="middle" '
            f'font-size="12" fill="#17252c">{owner}</text></g>'
        )
    buttons = []
    for owner, color in zip(owner_ids, colors, strict=True):
        owned = int(counts[owner - 1])
        buttons.append(
            f'<button data-select="{owner}" aria-pressed="false">'
            f'<span style="background:{to_hex(color)}"></span>'
            f"Owner {owner} · {owned} home{'s' if owned != 1 else ''}</button>"
        )
    (output / "ownership.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Ownership map and key</title><style>"
        "body{font:16px/1.5 system-ui;color:#17252c;margin:24px}"
        ".layout{display:grid;grid-template-columns:minmax(300px,2fr) minmax(240px,1fr);gap:24px}"
        "svg{width:100%;max-height:85vh}button{font:inherit;padding:8px;margin:3px;"
        "border:1px solid #bbb;border-radius:4px;background:white;cursor:pointer}"
        "button[aria-pressed=true]{outline:3px solid #245b91}span{display:inline-block;"
        "width:16px;height:16px;margin-right:8px;border:1px solid #888}"
        "#key{max-height:75vh;overflow:auto}g.dim{opacity:0.12}"
        "@media(max-width:700px){.layout{grid-template-columns:1fr}}</style>"
        "<h1>Who owns each home?</h1><p>Select an owner in the key to highlight all their "
        "properties. Cell labels are owner IDs; colors are categorical and reused. "
        "Homes in separate locations can belong to the same person.</p>"
        '<button id="reset">Show all owners</button><p id="status" aria-live="polite">'
        f"{len(owner_ids)} owners · {owners.size} homes. "
        "People without homes are omitted from the key."
        '</p><div class="layout">'
        f'<svg role="img" aria-label="Home grid labeled by owner ID" '
        f'viewBox="0 0 {spec.columns * 40} {spec.rows * 40}">' + "".join(cells) + "</svg>"
        '<section aria-label="Owner key"><h2>Owner key</h2><div id="key">'
        + "".join(buttons)
        + "</div></section></div><script>"
        'const groups=document.querySelectorAll("g[data-owner]");'
        'const buttons=document.querySelectorAll("[data-select]");'
        'function select(id){groups.forEach(g=>g.classList.toggle("dim",'
        "id!==null&&g.dataset.owner!==id));buttons.forEach(b=>"
        'b.setAttribute("aria-pressed",String(b.dataset.select===id)));'
        'document.getElementById("status").textContent=id===null?"Showing all owners":'
        "`Owner ${id}: ${[...groups].filter(g=>g.dataset.owner===id).length} homes highlighted`;}"
        'buttons.forEach(b=>b.addEventListener("click",()=>select(b.dataset.select)));'
        'document.getElementById("reset").addEventListener("click",()=>select(null));'
        "</script></html>"
    )

    order = np.argsort(incomes, kind="stable")
    population = np.arange(len(incomes) + 1) / len(incomes)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, amounts, power, title in zip(
        axes[:2],
        [incomes[order], counts[order]],
        [2, 3],
        ["Income Lorenz curve", "Ownership along income rank"],
        strict=True,
    ):
        ax.plot(population, population**power, label="Target curve")
        ax.plot(
            population,
            np.r_[0, np.cumsum(amounts) / amounts.sum()],
            linestyle="--",
            label="Realized allocation",
        )
        ax.plot([0, 1], [0, 1], color="gray", linewidth=0.7)
        ax.set(title=title, xlabel="Population share", ylabel="Resource share")
        ax.legend()
    axes[2].scatter(incomes[residents.ravel()] / 1000, prices.ravel() / 1000, s=12, alpha=0.6)
    axes[2].set(
        title="Residence placement (noise = 0.1)",
        xlabel="Resident annual income ($ thousands)",
        ylabel="Home price ($ thousands)",
    )
    save(
        "02-allocation",
        "Income preserves the annual budget exactly in cents. Ownership targets "
        "home counts; integer rounding causes small departures from the continuous curve.",
    )

    # Independent replicate fields: do not treat spatially correlated cells as iid samples.
    field_samples = 500
    smoothed = np.stack(
        [
            smooth_field(numpy_stream(spec.seed, f"check-field:{i}").normal(size=shape), 2)
            for i in range(field_samples)
        ]
    )
    price_samples = np.stack(
        [
            price_field(
                shape,
                reference_price=250000,
                spread=0.4,
                length_scale=2,
                rng=numpy_stream(spec.seed, f"check-price:{i}"),
            )
            for i in range(field_samples)
        ]
    )
    center = (spec.rows // 2, spec.columns // 2)
    values = smoothed[:, center[0], center[1]]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    x = np.linspace(-4, 4, 200)
    axes[0].hist(values, bins=25, density=True, alpha=0.6, label="500 independent fields")
    axes[0].plot(x, np.exp(-x * x / 2) / np.sqrt(2 * np.pi), label="N(0, 1)", color=ORANGE)
    axes[0].set(title="Same center cell across 500 new worlds", xlabel="Noise", ylabel="Density")
    axes[0].legend()
    im = axes[1].imshow(smoothed.var(axis=0), vmin=0.7, vmax=1.3, cmap=VARIANCE_COLORS)
    axes[1].set(title="At each cell: variance across 500 worlds\nWhite ≈ expected variance of 1")
    fig.colorbar(im, ax=axes[1])
    axes[2].hist(
        np.log(price_samples[:, center[0], center[1]] / 250000), bins=25, density=True, alpha=0.6
    )
    x = np.linspace(-1.6, 1.6, 200)
    axes[2].plot(x, np.exp(-0.5 * (x / 0.4) ** 2) / (0.4 * np.sqrt(2 * np.pi)), color=ORANGE)
    axes[2].set(
        title="Log price / reference at fixed center",
        xlabel="log(P / 250,000)",
        ylabel="Density; target N(0, 0.4²)",
    )
    save(
        "03-fields",
        "We generate 500 new noise fields using the same settings and different seeds. "
        "Left: take the center cell from every field, giving 500 values; their histogram "
        "should approximately follow the orange standard-normal curve (mean 0, variance 1). "
        "Middle: repeat that calculation at every cell. Each color measures how much that "
        "one location varies across the 500 fields. White is near the expected variance of 1; "
        "blue is lower and orange higher. With only 500 samples, small deviations are expected. "
        "This is not a map of differences between neighboring homes in one world. "
        "Smoothing correlates neighbors, so a single world need not have mean 0 or variance 1. "
        "Right: an additional 500 price fields test the price transformation at the center. "
        "The log of price divided by $250,000 should have mean 0 and variance 0.16 "
        "(standard deviation 0.4), following the orange curve.",
    )

    count_rng = numpy_stream(spec.seed, "diagnostic-counts")
    location_rng = numpy_stream(spec.seed, "diagnostic-locations")
    event_counts = np.empty(draws, dtype=np.int64)
    anchor_counts = np.zeros(probabilities.shape, dtype=np.int64)
    home_hits = np.zeros(shape, dtype=np.int64)
    for i in range(draws):
        anchors = sample_disasters(spec.rate, probabilities, count_rng, location_rng=location_rng)
        event_counts[i] = len(anchors)
        hit = np.zeros(shape, dtype=bool)
        for a, b in anchors:
            anchor_counts[a, b] += 1
            hit[a : a + 3, b : b + 3] = True
        home_hits += hit
    observed = anchor_counts / max(int(anchor_counts.sum()), 1)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    k = np.arange(max(int(event_counts.max()), 5) + 1)
    frequencies = np.bincount(event_counts, minlength=len(k)) / draws
    axes[0].bar(k, frequencies, alpha=0.6, label="Observed")
    axes[0].plot(
        k,
        [exp(-spec.rate) * spec.rate ** int(n) / factorial(int(n)) for n in k],
        "o-",
        label="Poisson expectation",
        color=ORANGE,
    )
    axes[0].set(title=f"Disaster counts ({draws:,} periods)", xlabel="Events", ylabel="Probability")
    axes[0].legend()
    axes[1].scatter(probabilities.ravel(), observed.ravel(), s=12)
    limit = max(probabilities.max(), observed.max())
    axes[1].plot([0, limit], [0, limit], color="gray")
    axes[1].set(
        title="Anchor frequencies", xlabel="Expected probability", ylabel="Observed frequency"
    )
    expected_hits = 1 - np.exp(-spec.rate * exposure)
    axes[2].scatter(expected_hits.ravel(), (home_hits / draws).ravel(), s=12)
    limit = expected_hits.max()
    axes[2].plot([0, limit], [0, limit], color="gray")
    axes[2].set(
        title="At least one hit per home per period",
        xlabel="Expected probability",
        ylabel="Observed frequency",
    )
    save(
        "04-disasters",
        "Independent numerical draws, without destroying a live world. "
        "Counts, anchor selection, and overlapping footprint exposure are tested separately.",
    )

    initial_capital = {i: float(f.capital) for i, f in world.insurers.items()}
    rows = []
    recorder = WorldRecorder(world)
    for _ in range(spec.periods):
        result = recorder.step()
        row = {
            "period": result.period,
            "events": len(result.disasters),
            "new_losses": sum(len(e.losses) for e in result.disasters),
            "destroyed": sum(h.destroyed for h in world.homes.values()),
            "displaced": sum(world.observe(i).residence is None for i in world.people),
            "claim_due": float(sum(c.due for c in result.claims)),
            "claim_paid": float(sum(c.paid for c in result.claims)),
        }
        row.update({f"capital_{i}": float(f.capital) for i, f in world.insurers.items()})
        rows.append(row)
    recorder.export(output)
    with (assets / "trajectory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    periods = [r["period"] for r in rows]
    axes[0].plot(periods, np.cumsum([r["events"] for r in rows]), label="Cumulative events")
    axes[0].plot(periods, [r["destroyed"] for r in rows], label="Destroyed homes")
    axes[0].plot(periods, [r["displaced"] for r in rows], "--", label="Displaced residents")
    axes[0].set(title="One world trajectory", xlabel="Period", ylabel="Count")
    axes[0].legend()
    for name in ("claim_due", "claim_paid"):
        axes[1].plot(periods, np.cumsum([r[name] for r in rows]) / 1e6, label=name)
    axes[1].set(title="Cumulative claims", xlabel="Period", ylabel="$ millions")
    axes[1].legend()
    for i in world.insurers:
        axes[2].plot(
            [0] + periods,
            [initial_capital[i] / 1e6] + [r[f"capital_{i}"] / 1e6 for r in rows],
            label=f"Firm {i}",
        )
    axes[2].set(title="Insurer capital", xlabel="Period", ylabel="$ millions")
    axes[2].legend()
    save(
        "05-trajectory",
        "One illustrative trajectory, not a multi-seed economic conclusion. "
        "Fixed cheapest-affordable quotes concentrate purchases at Firm 1. No rebuilding; "
        "repeated hits do not generate new building losses. Income and rent settle each period.",
    )
    summary = {
        "world": asdict(spec),
        "numpy": np.__version__,
        "matplotlib": matplotlib.__version__,
        "python": platform.python_version(),
        "diagnostic_periods": draws,
        "field_samples": field_samples,
        "annual_income_total": str(sum((p.annual_income or Decimal(0)) for p in scenario.people)),
        "home_count": len(scenario.homes),
        "ownership_total": int(counts.sum()),
        "contracts": len(world.contracts),
        "poisson_mean": float(event_counts.mean()),
        "poisson_variance": float(event_counts.var()),
        "expected_poisson_mean_variance": spec.rate,
        "anchor_total_variation": float(np.abs(observed - probabilities).sum() / 2),
        "home_hit_max_absolute_error": float(np.max(np.abs(home_hits / draws - expected_hits))),
        "smoothed_center_mean": float(values.mean()),
        "smoothed_center_variance": float(values.var()),
        "final_destroyed": rows[-1]["destroyed"],
        "claims_due": sum(r["claim_due"] for r in rows),
        "claims_paid": sum(r["claim_paid"] for r in rows),
        "limitations": [
            "Current per-period income/rent timing; report's 10/20-run schedule pending",
            "Public event history is not yet delivered to agent observations",
            "Fixed baseline policies, no Q-learning; illustrative uncalibrated parameters",
        ],
    }
    (assets / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    np.savez_compressed(
        assets / "numerical-data.npz",
        prices=prices,
        incomes=incomes,
        ownership_counts=counts,
        residents=residents,
        owners=owners,
        anchor_probabilities=probabilities,
        exposure=exposure,
        anchor_counts=anchor_counts,
        home_hits=home_hits,
        event_counts=event_counts,
        smoothed_fields=smoothed,
        price_fields=price_samples,
    )
    body = "".join(
        f'<figure><img src="assets/{name}.png"><figcaption>{caption} '
        f'<a href="assets/{name}.pdf">PDF</a></figcaption></figure>'
        for name, caption in figures
    )
    (output / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><title>Standard world diagnostics</title>'
        "<style>body{max-width:1200px;margin:40px auto;padding:0 20px;font:17px/1.6 system-ui;"
        "color:#17252c}img{width:100%}figure{margin:35px 0}figcaption{color:#425660}"
        "pre{overflow:auto;background:#f3f5f6;padding:20px}</style><h1>Standard world "
        "diagnostics</h1>"
        f"<p>Seed {spec.seed}; {spec.rows} × {spec.columns} homes; constant rate {spec.rate}; "
        "3 × 3 footprints; hidden risk contrast 1. Income and ownership exponents 2 and 3. "
        "Reference price $250,000, price spread 0.4, smoothing length 2, placement noise 0.1. "
        "Initial cash $10,000 per person and $10 million per insurer; mean annual income "
        "$50,000.</p>"
        "<p>This initializes the Standard numerical world. Payment timing, public-history "
        "delivery, "
        "and learned policies are unfinished. These diagnostics compare empirical samples with "
        "mathematical expectations; they do not prove correctness or establish economic "
        "findings.</p>"
        '<p><a href="diagnostics.html">Insurance Land diagnostics</a> · '
        '<a href="assets/summary.json">Summary and versions</a> · '
        '<a href="assets/trajectory.csv">Trajectory CSV</a> · '
        '<a href="assets/numerical-data.npz">Numerical arrays</a></p>' + body + "</html>"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("studies/webui"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--periods", type=int, default=120)
    parser.add_argument("--draws", type=int, default=20000)
    args = parser.parse_args()
    summary = generate(args.output, StandardWorld(seed=args.seed, periods=args.periods), args.draws)
    print(json.dumps(summary, indent=2))
    print(f"Report: {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
