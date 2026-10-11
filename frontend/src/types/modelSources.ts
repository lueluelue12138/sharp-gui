import type { ModelAsset } from '@/types/modelAsset';

export interface ModelSourceLink {
  source_id: string | null;
  model_count: number;
  total_count: number;
  default_model_id: string | null;
}

export interface ModelSourceLinksResponse {
  links: Record<string, ModelSourceLink>;
  repairing: boolean;
  revision: string | null;
}

export interface SourceModelsResponse extends ModelSourceLink {
  source_available?: boolean | null;
  source: { name?: string; media_type?: 'image' | 'video' };
  models: ModelAsset[];
  repairing: boolean;
}
