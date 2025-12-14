"""
Run PCA on archetype response matrix to determine optimal archetype count

Usage:
  python scripts/run_pca_analysis.py
"""

import pandas as pd
import numpy as np
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

def run_pca():
    """Run PCA on response matrix"""

    # Load matrix
    df = pd.read_csv('data/archetype_response_matrix.csv', index_col=0)
    print(f"Loaded matrix: {df.shape[0]} archetypes × {df.shape[1]} scenarios")

    # Run PCA
    pca = PCA()
    pca.fit(df.T)  # Transpose so scenarios are rows

    # Variance explained
    variance_explained = pca.explained_variance_ratio_
    cumulative_variance = np.cumsum(variance_explained)

    print("\n" + "="*60)
    print("PCA RESULTS")
    print("="*60)

    print("\nVariance Explained by Component:")
    for i, (var, cum_var) in enumerate(zip(variance_explained[:15], cumulative_variance[:15]), 1):
        print(f"  PC{i:2d}: {var*100:5.1f}%  (cumulative: {cum_var*100:5.1f}%)")

    # Find components needed for 90% variance
    n_components_90 = np.argmax(cumulative_variance >= 0.90) + 1
    print(f"\nComponents needed for 90% variance: {n_components_90}")
    print(f"Recommended archetype range: {n_components_90 + 6} to {n_components_90 + 10}")
    print("  (PCA components + buffer for interpretability)")

    # Scree plot
    plt.figure(figsize=(12, 6))

    plt.subplot(1, 2, 1)
    plt.plot(range(1, 21), variance_explained[:20], 'bo-')
    plt.axhline(y=0.05, color='r', linestyle='--', label='5% variance')
    plt.xlabel('Principal Component')
    plt.ylabel('Variance Explained')
    plt.title('Scree Plot')
    plt.grid(True, alpha=0.3)
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(range(1, 21), cumulative_variance[:20], 'go-')
    plt.axhline(y=0.90, color='r', linestyle='--', label='90% threshold')
    plt.xlabel('Principal Component')
    plt.ylabel('Cumulative Variance Explained')
    plt.title('Cumulative Variance')
    plt.grid(True, alpha=0.3)
    plt.legend()

    plt.tight_layout()
    plt.savefig('data/pca_scree_plot.png', dpi=150)
    print("\n✓ Saved scree plot to data/pca_scree_plot.png")

    return pca, n_components_90

if __name__ == "__main__":
    pca, n_components = run_pca()

    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("\n1. Review highly correlated archetypes (merge candidates)")
    print("2. Review low-discrimination scenarios (removal candidates)")
    print("3. Decide final archetype count (recommended: 18-22)")
    print("4. Create refined archetype set")
    print("\nSee: WEEK1_ARCHETYPE_IMPLEMENTATION_STATUS.md for details")
