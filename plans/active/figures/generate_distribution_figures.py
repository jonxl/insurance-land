"""Illustrative report figures; not simulation results or selected calibration.

Run from repository root:
uv run --with matplotlib --with numpy python plans/active/figures/generate_distribution_figures.py
"""
from pathlib import Path
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.dpi': 150})
BLUE, ORANGE = '#245b91', '#ba5a22'

def save(fig, name):
    fig.savefig(OUT / f'{name}.pdf', bbox_inches='tight')
    fig.savefig(OUT / f'{name}.png', bbox_inches='tight', dpi=150)
    plt.close(fig)

# Independent labeled risk stream under the same global seed.
def plot_hidden_risk():
    rows = columns = 8
    risk_length, contrast = 2.0, 1.0
    risk_rng = np.random.default_rng(np.random.SeedSequence([42, 1]))
    cells = np.indices((rows, columns)).reshape(2, -1).T
    distance = ((cells[:, None] - cells[None, :]) ** 2).sum(axis=2)
    kernel = np.exp(-distance / (2 * risk_length**2))
    risk_noise = risk_rng.normal(size=rows * columns)
    smooth = (kernel @ risk_noise) / np.sqrt((kernel**2).sum(axis=1))
    weights = np.exp(contrast * smooth.reshape(rows, columns))
    probability = weights / weights.sum()
    assert np.isclose(probability.sum(), 1) and np.all(probability > 0)
    height, width = probability.shape
    fig, ax = plt.subplots(figsize=(6, 4.8), layout='constrained')
    im = ax.imshow(100 * probability, cmap='Purples', interpolation='nearest',
                   origin='lower', extent=(.5, width+.5, .5, height+.5))
    ax.set(title='Hidden disaster risk', xlabel='Column b', ylabel='Row a',
           xticks=range(1, width+1), yticks=range(1, height+1))
    ax.set_xticks(np.arange(.5, width+1), minor=True)
    ax.set_yticks(np.arange(.5, height+1), minor=True)
    ax.grid(which='minor', color='white', linewidth=.4)
    ax.tick_params(which='minor', bottom=False, left=False)
    fig.colorbar(im, ax=ax, label='Probability of being the disaster center (%)')
    save(fig, 'hidden-spatial-risk')

plot_hidden_risk()

# Region sizes: one home per region, then the rest by a smoothed log-normal field.
def plot_region_sizes():
    rows = columns = 8
    mean_homes, contrast, length = 4, 1.0, 2.0
    rng = np.random.default_rng(np.random.SeedSequence([42, 2]))
    cells = np.indices((rows, columns)).reshape(2, -1).T
    distance = ((cells[:, None] - cells[None, :]) ** 2).sum(axis=2)
    kernel = np.exp(-distance / (2 * length**2))
    smooth = (kernel @ rng.normal(size=rows * columns)) / np.sqrt((kernel**2).sum(axis=1))
    weights = np.exp(contrast * smooth)
    spare = rows * columns * (mean_homes - 1)
    target = spare * weights / weights.sum()
    extra = np.floor(target + .5).astype(int)
    while extra.sum() != spare:
        step = 1 if extra.sum() < spare else -1
        extra[np.argmax(step * (target - extra))] += step
    sizes = (1 + extra).reshape(rows, columns)
    assert sizes.sum() == rows * columns * mean_homes and sizes.min() >= 1
    fig, ax = plt.subplots(figsize=(6, 4.8), layout='constrained')
    im = ax.imshow(sizes, cmap='YlOrBr', interpolation='nearest', origin='lower',
                   extent=(.5, columns+.5, .5, rows+.5))
    for (a, b), size in np.ndenumerate(sizes):
        ax.text(b + 1, a + 1, str(size), ha='center', va='center', fontsize=9,
                color='white' if size > sizes.max() * .6 else '#2e1c12')
    ax.set(title='Homes in each region', xlabel='Column b', ylabel='Row a',
           xticks=range(1, columns+1), yticks=range(1, rows+1))
    fig.colorbar(im, ax=ax, label='Homes')
    save(fig, 'region-sizes')

plot_region_sizes()

# Disaster size: a Tweedie of power 3/2 floored to a whole radius, against the earlier normal.
def tweedie_reach(d, mean=.3, dispersion=1.5):
    if d == 0:
        return 1.0
    rate, jump = 2 * math.sqrt(mean) / dispersion, dispersion * math.sqrt(mean) / 2
    x, jumps, term, erlang, total = d / jump, math.exp(-rate), math.exp(-d / jump), 0.0, 0.0
    for n in range(1, 400):
        jumps *= rate / n
        erlang += term
        term *= x / n
        total += jumps * erlang
    return total

def plot_disaster_sizes():
    PURPLE = '#4a2496'
    GRAY = '#8a847c'
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), layout='constrained')
    tail = [tweedie_reach(d) for d in range(8)]
    normal = [math.erfc(d / math.sqrt(2)) for d in range(8)]
    mass = [tail[0] - tail[1], tail[1] - tail[2], tail[2] - tail[3], tail[3]]
    labels = ['1 × 1', '3 × 3', '5 × 5', '7 × 7 or larger']
    shades = ['#d9d6d1', '#b9a6dc', '#7f5fc0', PURPLE]
    bars = axes[0].bar(labels, mass, color=shades, width=.6)
    for bar, value in zip(bars, mass):
        axes[0].text(bar.get_x() + bar.get_width() / 2, value + .02, f'{100*value:.2f}%',
                     ha='center', fontsize=9)
    axes[0].set(title='Zone size in regions', xlabel=r'Side length $2r_e+1$',
                ylabel='Probability', ylim=(0, 1.05))
    radii = range(1, 8)
    axes[1].semilogy(radii, normal[1:], color=GRAY, marker='o', ms=3.5, lw=1.2,
                     label='Earlier standard normal')
    axes[1].semilogy(radii, tail[1:], color=PURPLE, marker='o', ms=3.5, lw=1.4, label='Tweedie')
    axes[1].set(title='Chance a zone reaches a given radius', xlabel='Radius d',
                ylabel=r'$\Pr(r_e\geq d)$', xticks=list(radii), ylim=(1e-12, 1))
    axes[1].legend(frameon=False)
    save(fig, 'disaster-sizes')

plot_disaster_sizes()

# Regenerate the new figure alone without rewriting the existing illustrations.
if __name__ == '__main__':
    import sys
    if '--risk-only' in sys.argv:
        raise SystemExit(0)

# Price field: exactly the normalized finite-grid Gaussian construction in the text.
m = n = 8
seed, reference, spread, length = 42, 250000, .4, 2.0
rng = np.random.default_rng(seed)
positions = np.indices((m, n)).reshape(2, -1).T
squared_distance = ((positions[:, None] - positions[None, :]) ** 2).sum(axis=2)
weights = np.exp(-squared_distance / (2 * length**2))
noise = rng.normal(size=m*n)
field = (weights @ noise) / np.sqrt((weights**2).sum(axis=1))
prices = reference * np.exp(spread * field.reshape(m, n))
fig, ax = plt.subplots(figsize=(6, 4.8), layout='constrained')
im = ax.imshow(prices / 1000, cmap='YlOrBr', interpolation='nearest', origin='lower', extent=(.5, n+.5, .5, m+.5))
ax.set(title='Initial home prices by region', xlabel='Column b', ylabel='Row a', xticks=range(1,n+1), yticks=range(1,m+1))
ax.set_xticks(np.arange(.5, n+1), minor=True)
ax.set_yticks(np.arange(.5, m+1), minor=True)
ax.grid(which='minor', color='white', linewidth=.4)
ax.tick_params(which='minor', bottom=False, left=False)
fig.colorbar(im, ax=ax, label='Home price (thousand dollars)')
save(fig, 'initial-prices')

# Lorenz curves are cumulative share functions, not probability densities.
N = H = 12
mean = 50000
p = np.linspace(0, 1, 401)
boundaries = np.arange(N + 1) / N
y = N * mean * np.diff(boundaries**2)
a = H * np.diff(boundaries**3)
h = np.floor(a + .5).astype(int)
rng = np.random.default_rng(42)
while h.sum() != H:
    residual = a - h if h.sum() < H else h - a
    if h.sum() > H:
        residual = np.where(h > 0, residual, -np.inf)
    candidates = np.flatnonzero(np.isclose(residual, residual.max(), rtol=0, atol=1e-12))
    chosen = rng.choice(candidates)
    h[chosen] += 1 if h.sum() < H else -1
assert h.sum() == H and np.all(h >= 0)
fig, axes = plt.subplots(2, 2, figsize=(10, 6.3), layout='constrained')
for ax in axes[0]:
    ax.plot(p, p, color='0.65', ls='--', lw=1, label='Equal shares')
    ax.set(xlim=(0,1), ylim=(0,1), xlabel='Cumulative population share p', ylabel='Cumulative resource share')
axes[0,0].plot(p, p**2, color=BLUE, label=r'Target $L_y(p)=p^2$')
axes[0,0].plot(boundaries, np.r_[0, np.cumsum(y)] / y.sum(), 'o-', ms=3, color=ORANGE, label='12-agent cumulative shares')
axes[0,0].set_title('Income Lorenz curve')
axes[0,1].plot(p, p**3, color=BLUE, label=r'Target $L_h(p)=p^3$')
axes[0,1].plot(boundaries, np.r_[0, np.cumsum(h)] / H, 'o-', ms=3, color=ORANGE, label='After whole-home rounding')
axes[0,1].set_title('Ownership Lorenz curve')
for ax in axes[0]:
    ax.legend(fontsize=8, loc='upper left')
rank = np.arange(1, N+1)
axes[1,0].bar(rank, y / 1000, color=BLUE)
axes[1,0].set(title='Assigned income by agent', xlabel='Agent i, ordered by income', ylabel='Annual income (thousand dollars)')
axes[1,1].scatter(rank, a, facecolors='none', edgecolors=ORANGE, s=45, label='Fractional target')
axes[1,1].bar(rank, h, width=.55, color=BLUE, alpha=.8, label='Integer home count')
axes[1,1].set(title='Assigned homes by agent', xlabel='Agent i, same income ordering', ylabel='Homes owned', yticks=np.arange(0, 4))
axes[1,1].legend(fontsize=8)
for ax in axes[1]:
    ax.set_xticks(rank)
    ax.set_ylim(bottom=0)
save(fig, 'lorenz-allocations')

fig, axes = plt.subplots(1, 3, figsize=(10, 3.1), layout='constrained', sharey=True)
k = np.arange(9)
for ax, lam in zip(axes, [.1, 1, 2]):
    mass = np.array([math.exp(-lam) * lam**int(j) / math.factorial(int(j)) for j in k])
    ax.bar(k, mass, width=.6, color=BLUE)
    ax.set(title=rf'$\lambda={lam:g}$ per period', xlabel='Event count k', xticks=k, ylim=(0,1))
axes[0].set_ylabel(r'Probability $\Pr(K_t=k)$')
save(fig, 'poisson-counts')
