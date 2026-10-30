export interface UsageCategory {
  category: string;
  calls: number;
  total_tokens: number;
  audio_seconds: number;
  unreported_calls: number;
  unpriced_calls: number;
  estimated_cost: string | null;
  currency: string;
}
