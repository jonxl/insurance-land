// Recording values mirror the Python JSON exporter; money stays decimal text.
export type Money = string | number;
export interface Person {
  id: number;
  cash: Money;
  income: Money;
  annual_income: Money;
}
export interface Home {
  id: number;
  owner: number;
  resident: number | null;
  value: Money;
  rent: Money;
  destroyed: boolean;
  position: [number, number];
}
export interface Firm {
  id: number;
  name: string;
  capital: Money;
}
export interface Disaster {
  id: number;
  cells: [number, number][];
  losses: number[];
  displaced: number[];
}
export interface Transfer {
  kind: 'income' | 'rent' | 'premium' | 'claim';
  person: number;
  amount: Money;
  home?: number;
  firm?: number;
  recipient?: number;
  paid?: boolean;
  requested?: Money;
  due?: Money;
  shortfall?: Money;
}
export interface Frame {
  period: number;
  people: Person[];
  homes: Home[];
  firms: Firm[];
  events: Disaster[];
  transfers: Transfer[];
  actions: { person: number; action: string; paid: boolean | null }[];
}
export interface Contract {
  id: number;
  person: number;
  firm: number;
  home: number;
  product: string;
  starts: number;
  ends: number;
}
export interface Configuration {
  name: string;
  seed: number;
  rows: number;
  columns: number;
  periods: number;
  rate: number;
  chaos_rate_ratio: number;
  homes_per_region: number;
  radius_mean: number;
  radius_dispersion: number;
}
export interface Recording {
  frames: Frame[];
  contracts: Contract[];
  configuration?: Configuration;
  rates?: number[];
  timing?: string;
  insurance_initialization?: string;
  insurance_assignments?: Record<number, number>;
  diagnostics?: {
    settings?: Record<string, number>;
    hit_probability_per_event?: number[][];
    income_lorenz?: number[];
    ownership_lorenz?: number[];
  };
}
export interface WorldBundle {
  worlds: Record<string, Recording>;
  default?: string;
  title?: string;
}
export type RecordingBundle = WorldBundle | (Recording & { title?: string });
export interface MetricValue {
  id: number;
  value: number;
}
export interface Region {
  col: number;
  row: number;
  count: number;
}
export interface Rectangle {
  x: number;
  y: number;
  w: number;
  h: number;
}
