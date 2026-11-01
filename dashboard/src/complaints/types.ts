export type ComplaintCategory = "wifi" | "slow" | "disconnect" | "other";

export interface ComplaintMarker {
  id: string;
  buildingId: string;
  category: ComplaintCategory;
  text: string;
  reportedAt: string;
}

export interface ComplaintCluster {
  buildingId: string;
  count: number;
  byCategory: Record<string, number>;
  latest: ComplaintMarker[];
}

export interface ComplaintSource {
  readonly label: string;
  readonly isSample: boolean;
  list(): Promise<ComplaintMarker[]>;
}
