/**
 * Small, pure presentational primitives. Props in, JSX out — no data fetching, no client.
 * Accessibility is built in: `Field` associates label + hint + error with the control via ids,
 * `Button` forwards refs and exposes a busy state, and status messages use the right ARIA roles.
 */

import { forwardRef, useId, type ButtonHTMLAttributes, type ReactNode } from 'react';

// ---- Button ----

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost';
  busy?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', busy = false, disabled, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`btn btn--${variant} ${className ?? ''}`.trim()}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="btn__spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
});

// ---- Field (label + control + hint + error association) ----

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  /** Render the control with the generated `id` + `aria-describedby`. */
  children: (props: { id: string; describedBy: string | undefined }) => ReactNode;
}): JSX.Element {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(' ') || undefined;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {children({ id, describedBy })}
      {hint ? (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="field__error" id={errId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ---- status / feedback ----

export function Loading({ label = 'Loading…' }: { label?: string }): JSX.Element {
  return (
    <p className="loading" role="status">
      <span className="loading__spinner" aria-hidden="true" /> {label}
    </p>
  );
}

export function ErrorMessage({ error }: { error: Error }): JSX.Element {
  return (
    <p className="message message--error" role="alert">
      {error.message}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }): JSX.Element {
  return <p className="empty-state">{children}</p>;
}

/** A callout banner. `tone="warn"` for the non-negotiable honesty notices. */
export function Banner({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn';
  title?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <aside className={`banner banner--${tone}`} role="note">
      {title ? <p className="banner__title">{title}</p> : null}
      <div className="banner__body">{children}</div>
    </aside>
  );
}

/** A labelled scalar shown as "term: value" — used across the summary cards. */
export function Stat({ term, value }: { term: string; value: ReactNode }): JSX.Element {
  return (
    <div className="stat">
      <dt className="stat__term">{term}</dt>
      <dd className="stat__value">{value}</dd>
    </div>
  );
}
