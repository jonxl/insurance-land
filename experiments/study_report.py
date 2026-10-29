"""Build the three-world explanatory report from the recorded diagnostic worlds."""

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments.worlds import WorldSpec
from utils.distributions import numpy_stream, price_field, sample_disasters, smooth_field

BLUE, ORANGE, PURPLE = "#245b91", "#ba5a22", "#6a51a3"


def generate(output: Path, *, draws: int = 20000, field_samples: int = 500) -> None:
    if draws < 1 or field_samples < 2:
        raise ValueError("Require positive draws and at least two fields")
    bundle = json.loads((output / "assets" / "world-history.json").read_text())
    plt.rcParams.update(
        {"figure.dpi": 150, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    sections = []
    summaries = {}
    descriptions = {
        "Peace": "Equal annual income, one owner-occupied home per person, equal initial cash, "
        "and identical initial home prices. Disaster risk is still spatially unequal. "
        "There is no redistribution after initialization.",
        "Standard": "Unequal income and ownership allocations, spatially varying prices, and "
        "income-based residence placement with noise. The disaster rate is constant.",
        "Chaos": "The same initial population, ownership, prices and hidden risk as “Standard”. "
        "Only the disaster-rate schedule changes: it grows exponentially. The schedule "
        "is normalized to match “Standard”’s expected total number of events.",
    }
    for name, data in bundle["worlds"].items():
        spec = WorldSpec(**data["configuration"])
        config = spec.population()
        frames = data["frames"]
        first, last = frames[0], frames[-1]
        shape = (spec.rows, spec.columns)
        rates = np.array(data["rates"])
        target = output / "assets" / name.lower()
        target.mkdir(parents=True, exist_ok=True)
        figures: list[str] = []

        def save(
            slug: str,
            title: str,
            caption: str,
            *,
            name: str = name,
            target: Path = target,
            figures: list[str] = figures,
        ) -> None:
            plt.gcf().suptitle(f"“{name}” · {title}", fontsize=14)
            plt.gcf().tight_layout()
            for extension in ("png", "pdf"):
                plt.savefig(target / f"{slug}.{extension}")
            plt.close()
            base = f"assets/{name.lower()}/{slug}"
            figures.append(
                f'<figure><img loading="lazy" src="{base}.png" '
                f'alt="{title} for the {name} world"><figcaption>{caption} '
                f'<a href="{base}.pdf">PDF</a></figcaption></figure>'
            )

        homes = first["homes"]
        people = first["people"]
        prices = np.array([float(h["value"]) for h in homes]).reshape(shape)
        incomes = np.array([float(p["annual_income"]) for p in people])
        counts = np.bincount([h["owner"] - 1 for h in homes], minlength=len(people))
        residents = np.array([h["resident"] - 1 for h in homes]).reshape(shape)
        probabilities = spec.disasters().risk_probabilities(shape, seed=spec.seed)
        exposure = np.zeros(shape)
        for (a, b), probability in np.ndenumerate(probabilities):
            exposure[a : a + 3, b : b + 3] += probability
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        for ax, values, title, cmap in zip(
            axes,
            [prices / 1000, incomes[residents] / 1000, 100 * (1 - np.exp(-rates[0] * exposure))],
            [
                "Initial home prices ($ thousands)",
                "Resident income ($ thousands / year)",
                "First-period exposure (%)",
            ],
            ["YlOrBr", "YlOrBr", "Purples"],
            strict=True,
        ):
            im = ax.imshow(values, cmap=cmap, interpolation="nearest")
            ax.set(title=title, xlabel="Column", ylabel="Row")
            fig.colorbar(im, ax=ax, shrink=0.8)
        save(
            "world",
            "Initial world",
            "Each square is a home. Orange maps show initial prices "
            "and the annual income of its resident. Purple shows the probability of at least one "
            "hit in the first period, including all overlapping 3 × 3 footprints. "
            "In “Chaos”, this probability increases over time. Color scales are labeled per panel; "
            "a uniform map means identical values, not missing data.",
        )

        population = np.arange(len(people) + 1) / len(people)
        order = np.argsort(incomes, kind="stable")
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        for ax, amounts, exponent, title in zip(
            axes[:2],
            [incomes[order], counts[order]],
            [1 if name == "Peace" else 2, 1 if name == "Peace" else 3],
            ["Income allocation", "Home ownership along income rank"],
            strict=True,
        ):
            ax.plot(population, population**exponent, color=BLUE, label="Target")
            ax.plot(
                population,
                np.r_[0, np.cumsum(amounts) / amounts.sum()],
                "--",
                color=ORANGE,
                label="Realized",
            )
            ax.set(title=title, xlabel="Population share", ylabel="Resource share")
            ax.legend()
        unique, frequency = np.unique(counts, return_counts=True)
        axes[2].bar(unique, frequency, color=BLUE)
        axes[2].set(
            title="Homes owned per person", xlabel="Number of homes", ylabel="People", xticks=unique
        )
        save(
            "allocation",
            "Allocation checks",
            "The cumulative curves compare the intended "
            "resource distribution with the actual population. Income is allocated exactly in "
            "cents; ownership is rounded to whole homes while conserving the total. The bars "
            "include people with zero homes. “Peace” starts with equality; the other two worlds "
            "share the same unequal allocations. These describe initialization, before disasters.",
        )

        fields = np.stack(
            [
                smooth_field(
                    numpy_stream(spec.seed, f"check-field:{i}").normal(size=shape),
                    config.length_scale,
                )
                for i in range(field_samples)
            ]
        )
        price_fields = np.stack(
            [
                price_field(
                    shape,
                    reference_price=float(config.reference_price),
                    spread=config.price_spread,
                    length_scale=config.length_scale,
                    rng=numpy_stream(spec.seed, f"check-price:{i}"),
                )
                for i in range(field_samples)
            ]
        )
        center = (spec.rows // 2, spec.columns // 2)
        values = fields[:, center[0], center[1]]
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        axes[0].hist(values, bins=25, density=True, color=BLUE, alpha=0.7)
        x = np.linspace(-4, 4, 200)
        axes[0].plot(x, np.exp(-x * x / 2) / np.sqrt(2 * np.pi), color=ORANGE)
        axes[0].set(
            title="Same location across new worlds", xlabel="Smoothed noise", ylabel="Density"
        )
        im = axes[1].imshow(fields.var(axis=0), cmap="Blues", vmin=0, vmax=2)
        axes[1].set(title="Variance at each location\nExpected value: 1")
        fig.colorbar(im, ax=axes[1], shrink=0.8)
        logs = np.log(price_fields[:, center[0], center[1]] / float(config.reference_price))
        if config.price_spread == 0:
            axes[2].axvline(0, color=BLUE, linewidth=3, label="All samples = 0")
            axes[2].set_xlim(-0.5, 0.5)
            axes[2].legend()
        else:
            axes[2].hist(logs, bins=25, density=True, color=BLUE, alpha=0.7)
            x = np.linspace(-1.6, 1.6, 200)
            axes[2].plot(
                x,
                np.exp(-0.5 * (x / config.price_spread) ** 2)
                / (config.price_spread * np.sqrt(2 * np.pi)),
                color=ORANGE,
            )
        axes[2].set(title="Log price / reference", xlabel="log(P / 250,000)")
        save(
            "fields",
            "Noise and price checks",
            f"Generate {field_samples} independent fields "
            "with the same settings and different seeds. Left: collect the center cell from each "
            "field; those values should follow the orange standard-normal curve. Middle: each "
            "cell measures variation at that fixed location across worlds, with expected variance "
            "1. A single world need not itself have variance 1. Right: repeat with independently "
            "generated price fields. “Peace” has zero price spread, so every price is $250,000 "
            "and every log ratio is exactly zero; the other worlds target log-price variance 0.16.",
        )

        diagnostic_rates = np.resize(rates, draws)
        count_rng = numpy_stream(spec.seed, "diagnostic-counts")
        location_rng = numpy_stream(spec.seed, "diagnostic-locations")
        events = np.zeros(draws, dtype=int)
        hits = np.zeros(shape, dtype=int)
        anchors_count = np.zeros(probabilities.shape, dtype=int)
        for i, rate in enumerate(diagnostic_rates):
            anchors = sample_disasters(
                float(rate), probabilities, count_rng, location_rng=location_rng
            )
            events[i] = len(anchors)
            hit = np.zeros(shape, dtype=bool)
            for a, b in anchors:
                anchors_count[a, b] += 1
                hit[a : a + 3, b : b + 3] = True
            hits += hit
        k = np.arange(max(int(events.max()), 5) + 1)
        # A mixture of period-specific Poisson distributions, not Poisson(mean rate).
        mass = np.exp(-diagnostic_rates)
        expected_mass = [float(mass.mean())]
        for n in k[1:]:
            mass = mass * diagnostic_rates / n
            expected_mass.append(float(mass.mean()))
        expected_hits = np.mean([1 - np.exp(-r * exposure) for r in diagnostic_rates], axis=0)
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        axes[0].bar(
            k,
            np.bincount(events, minlength=len(k)) / draws,
            color=BLUE,
            alpha=0.7,
            label="Observed",
        )
        axes[0].plot(k, expected_mass, "o-", color=ORANGE, label="Expected")
        axes[0].set(title="Counts across sampled periods", xlabel="Events", ylabel="Probability")
        axes[0].legend()
        axes[1].scatter(expected_hits.ravel(), (hits / draws).ravel(), s=10, color=BLUE)
        limit = float(expected_hits.max())
        axes[1].plot([0, limit], [0, limit], color=ORANGE)
        axes[1].set(
            title="Home exposure", xlabel="Expected hit probability", ylabel="Observed frequency"
        )
        t = np.arange(1, len(frames))
        axes[2].plot(t, [len(f["events"]) for f in frames[1:]], color=BLUE, label="Recorded events")
        axes[2].plot(t, rates, color=ORANGE, label="Expected rate")
        axes[2].set(
            title="Recorded world rate schedule", xlabel="Period", ylabel="Events per period"
        )
        axes[2].legend()
        save(
            "disasters",
            "Disaster checks",
            f"Left and middle use {draws:,} fresh diagnostic "
            "periods, cycling through this world’s rate schedule without destroying homes. "
            "Observed samples should approach the expected curve and diagonal. For “Chaos”, "
            "the count expectation is a mixture of Poisson distributions at different rates—not "
            "a Poisson distribution at the average rate. Right shows the actual recorded world. "
            "Realized counts fluctuate; they need not rise every period even in “Chaos”.",
        )

        def claims(frame: dict[str, Any], key: str) -> float:
            return sum(float(t[key]) for t in frame["transfers"] if t["kind"] == "claim")

        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        t = np.arange(len(frames))
        axes[0].plot(
            t,
            [sum(h["destroyed"] for h in f["homes"]) for f in frames],
            color=BLUE,
            label="Destroyed homes",
        )
        axes[0].plot(
            t,
            [len(f["people"]) - sum(h["resident"] is not None for h in f["homes"]) for f in frames],
            "--",
            color=ORANGE,
            label="Displaced people",
        )
        axes[0].set(title="Housing outcomes", xlabel="Period", ylabel="Count")
        axes[0].legend()
        for key, label, color in [("due", "Due", BLUE), ("amount", "Paid", ORANGE)]:
            axes[1].plot(
                t, np.cumsum([claims(f, key) for f in frames]) / 1e6, color=color, label=label
            )
        axes[1].set(title="Cumulative claims", xlabel="Period", ylabel="$ millions")
        axes[1].legend()
        for firm, color in zip(first["firms"], [BLUE, ORANGE, PURPLE], strict=True):
            axes[2].plot(
                t,
                [
                    float(next(x for x in f["firms"] if x["id"] == firm["id"])["capital"]) / 1e6
                    for f in frames
                ],
                color=color,
                label=f"Firm {firm['name']}",
            )
        axes[2].set(title="Insurer capital", xlabel="Period", ylabel="$ millions")
        axes[2].legend()
        save(
            "outcomes",
            "Recorded outcomes",
            "These charts use the exact snapshots shown in "
            "diagnostics. Destroyed-home and displacement lines overlap because everyone starts "
            "housed and there is no relocation or rebuilding. The gap between claims due and paid "
            "is a capital shortfall, not uninsured property loss. Fixed cheapest-affordable "
            "purchases concentrate coverage at Firm A; idle competitors keep their capital. "
            "One seeded trajectory illustrates behavior, not a general economic conclusion.",
        )
        summary = {
            "configuration": data["configuration"],
            "rates": data["rates"],
            "diagnostic_draws": draws,
            "field_samples": field_samples,
            "event_mean": float(events.mean()),
            "expected_event_mean": float(diagnostic_rates.mean()),
            "event_variance": float(events.var()),
            "expected_event_variance": float(diagnostic_rates.mean() + diagnostic_rates.var()),
            "noise_center_variance": float(values.var()),
            "destroyed": sum(h["destroyed"] for h in last["homes"]),
            "claims_due": sum(claims(f, "due") for f in frames),
            "claims_paid": sum(claims(f, "amount") for f in frames),
        }
        summaries[name] = summary
        (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        np.savez_compressed(
            target / "diagnostic-samples.npz",
            noise_fields=fields,
            price_fields=price_fields,
            counts=events,
            diagnostic_rates=diagnostic_rates,
            home_hits=hits,
            anchor_counts=anchors_count,
        )
        sections.append(
            f'<section id="{name.lower()}" class="world-section" '
            f'aria-labelledby="heading-{name.lower()}"><h2 id="heading-{name.lower()}">'
            f"“{name}”</h2><p>{descriptions[name]}</p>"
            f'<p class="facts">{spec.rows} × {spec.columns} homes · Seed {spec.seed} · '
            f"{spec.periods} periods · Expected events {rates.sum():.1f} · "
            f"Rate {rates[0]:.3f} → {rates[-1]:.3f}</p>"
            f'<p><a href="assets/{name.lower()}/summary.json">Summary</a> · '
            f'<a href="assets/{name.lower()}/diagnostic-samples.npz">Sample arrays</a></p>'
            + "".join(figures)
            + "</section>"
        )
    (output / "assets" / "study-summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    html = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Insurance Land · World studies</title><style>
body{max-width:1200px;
margin:28px auto;
padding:0 20px;
font:15px/1.6 system-ui;
color:#24313a}
h1,h2{text-wrap:balance}p{text-wrap:pretty}header{display:flex;
justify-content:space-between;
align-items:center}
a{color:#245b91}button{font:inherit;
background:white;
border:1px solid #d8dfe3;
border-radius:5px;
padding:6px 16px;
cursor:pointer}
button[aria-pressed=true]{background:#eaf2f8;
border-color:#245b91;
color:#245b91}
button:focus-visible{outline:2px solid #245b91;
outline-offset:3px}nav{display:flex;
gap:8px;
margin:22px 0}
figure{margin:28px 0 40px}img{width:100%;
display:block}figcaption,.facts{color:#53616b}
.facts{font-variant-numeric:tabular-nums}.world-section[hidden]{display:none}
</style><header><h1>Insurance Land</h1><a href="diagnostics.html">Open diagnostics →</a></header>
<p>The same five checks for “Peace”, “Standard”, and “Chaos”: initial geography, resource
allocations,
noise and prices, disaster sampling, and recorded outcomes. Switch worlds to compare their
explanations and figures.</p>
<p>All worlds share the seed, population, initial cash budget, annual income budget,
insurer capital,
3 × 3 footprint, hidden risk field, insurance terms, and baseline policies. “Chaos” grows
tenfold from
its first-period rate to its last-period rate;
 its expected event total matches the other worlds.</p>
<details><summary>Scope of this study</summary><p>Parameters are illustrative, not calibrated.
Income and rent currently settle each period;
 the proposed 10/20-run payment clock is unfinished.
Agents do not yet receive public disaster history. These are fixed baseline policies, not
Q-learning.
Period zero is after opening premiums. Sampled statistical agreement supports the numerical tests;

it does not prove the model correct or establish causal findings from one seed.</p></details>
<nav aria-label="World selection">"""
    html += "".join(
        f'<button data-world="{name.lower()}" aria-pressed="false">“{name}”</button>'
        for name in summaries
    )
    html += (
        "</nav>"
        + "".join(sections)
        + """<script>
function choose(name){document.querySelectorAll('.world-section').forEach(s=>s.hidden=s.id!==name);
document.querySelectorAll('[data-world]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.world===name)));
history.replaceState(null,'','#'+name);}
document.querySelectorAll('[data-world]').forEach(b=>b.onclick=()=>choose(b.dataset.world));
choose(['peace','standard','chaos'].includes(location.hash.slice(1))?location.hash.slice(1):'standard');
</script></html>"""
    )
    (output / "index.html").write_text(html)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("studies/webui"))
    parser.add_argument("--draws", type=int, default=20000)
    args = parser.parse_args()
    generate(args.output, draws=args.draws)
    print(f"Report: {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
