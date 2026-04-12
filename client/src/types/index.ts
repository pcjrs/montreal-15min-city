export interface Facility {
  facility_name: string;
  category: "healthcare" | "education" | "cultural" | "recreation";
  facility_type: string;
  lat: number;
  lon: number;
}

export interface TransitStop {
  stop_id: string;
  stop_name: string;
  stop_lat: number;
  stop_lon: number;
  agency: "STM" | "STL";
  wheelchair_boarding: number;
  avg_headway_min: number | null;
  departures: number | null;
}

export interface FSA {
  postal_code: string;
  fsa_name: string;
  borough: string;
  longitude: number;
  latitude: number;
  population: number;
  total_dwellings: number;
}

export interface CategoryDetail {
  category: string;
  count: number;
  expected: number;
  adequacy_ratio: number;
  score: number;
  present: boolean;
  actual: number;
}

export interface FSAScore {
  postal_code: string;
  fsa_name: string;
  population: number;
  latitude: number;
  longitude: number;
  score: number;
  density_score: number;
  legacy_score: number;
  category_details: CategoryDetail[];
  categories: string[];
  missing: string[];
  stop_count: number;
  avg_headway_min: number | null;
  wheelchair_pct: number;
}

export interface BoroughScore {
  borough: string;
  total_population: number;
  fsa_count: number;
  average_score: number;
  fsa_scores: FSAScore[];
  underserved_fsas: FSAScore[];
  underserved_population: number;
}

export interface DesertData {
  postal_code: string;
  borough: string;
  population: number;
  latitude: number;
  longitude: number;
  stop_count: number;
  avg_headway: number | null;
  healthcare: number;
  education: number;
  cultural: number;
  recreation: number;
  score: number;
  density_score: number;
  legacy_score: number;
  category_details: CategoryDetail[];
}

export interface ChatResponse {
  type: string;
  message: string;
  data?: any;
}
