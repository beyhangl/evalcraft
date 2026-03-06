import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SkeletonLine, SkeletonCard, SkeletonTable } from '../components/Skeleton';

describe('SkeletonLine', () => {
  it('renders with default props', () => {
    const { container } = render(<SkeletonLine />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toBeTruthy();
    expect(el.style.width).toBe('100%');
  });

  it('accepts custom width and height', () => {
    const { container } = render(<SkeletonLine width="50%" height={20} />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.width).toBe('50%');
    expect(el.style.height).toBe('20px');
  });
});

describe('SkeletonCard', () => {
  it('renders with inner skeleton lines', () => {
    const { container } = render(<SkeletonCard />);
    // Should have a card div with skeleton lines inside
    expect(container.firstElementChild).toBeTruthy();
    expect(container.firstElementChild!.children.length).toBeGreaterThanOrEqual(2);
  });

  it('accepts custom height', () => {
    const { container } = render(<SkeletonCard height={200} />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.height).toBe('200px');
  });
});

describe('SkeletonTable', () => {
  it('renders specified number of rows', () => {
    const { container } = render(<SkeletonTable rows={3} />);
    const card = container.firstElementChild!;
    // 1 header + 3 rows = 4 children
    expect(card.children.length).toBe(4);
  });

  it('defaults to 5 rows', () => {
    const { container } = render(<SkeletonTable />);
    const card = container.firstElementChild!;
    // 1 header + 5 rows = 6 children
    expect(card.children.length).toBe(6);
  });
});
