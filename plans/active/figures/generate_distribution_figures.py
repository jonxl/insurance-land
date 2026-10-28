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

# Price field: exactly the normalized finite-grid Gaussian construction in the text.
m = n = 16
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
ax.set(title='Initial home prices', xlabel='Column b', ylabel='Row a', xticks=[1,4,8,12,16], yticks=[1,4,8,12,16])
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
axes[0,0].plot(boundaries, np.r_[0, np.cumsum(y)] / y.sum(), 'o-', ms=3, color=ORANGE, label='12-person cumulative shares')
axes[0,0].set_title('Income Lorenz curve')
axes[0,1].plot(p, p**3, color=BLUE, label=r'Target $L_h(p)=p^3$')
axes[0,1].plot(boundaries, np.r_[0, np.cumsum(h)] / H, 'o-', ms=3, color=ORANGE, label='After whole-home rounding')
axes[0,1].set_title('Ownership Lorenz curve')
for ax in axes[0]:
    ax.legend(fontsize=8, loc='upper left')
rank = np.arange(1, N+1)
axes[1,0].bar(rank, y / 1000, color=BLUE)
axes[1,0].set(title='Assigned income by person', xlabel='Person i, ordered by income', ylabel='Annual income (thousand dollars)')
axes[1,1].scatter(rank, a, facecolors='none', edgecolors=ORANGE, s=45, label='Fractional target')
axes[1,1].bar(rank, h, width=.55, color=BLUE, alpha=.8, label='Integer home count')
axes[1,1].set(title='Assigned homes by person', xlabel='Person i, same income ordering', ylabel='Homes owned', yticks=np.arange(0, 4))
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
