// Source: design-references/iitbbs-campus-map-research-package/iitbbs-campus-map-data.json
// (map_type: "Diagrammatic, not-to-scale campus orientation map"). Positions are SVG pixels,
// schematic only, not surveyed coordinates.

export interface CampusFeature {
  id: string;
  name: string;
  short: string;
  category: string;
  x: number;
  y: number;
}

export const CAMPUS_FEATURES: CampusFeature[] = [
  { id: "main-gate", name: "Main Gate", short: "MAIN GATE", category: "access", x: 620, y: 1015 },
  { id: "admin", name: "Administrative Building", short: "ADMIN BUILDING", category: "administration", x: 650, y: 620 },
  { id: "sbs", name: "School of Basic Sciences", short: "SBS", category: "academic", x: 400, y: 900 },
  { id: "seocs", name: "School of Earth, Ocean and Climate Sciences", short: "SEOCS", category: "academic", x: 245, y: 650 },
  { id: "secs", name: "School of Electrical and Computer Sciences", short: "SECS", category: "academic", x: 535, y: 865 },
  { id: "shssm", name: "School of Humanities, Social Sciences and Management", short: "SHSSM", category: "academic", x: 245, y: 515 },
  { id: "sif", name: "School of Infrastructure", short: "SIF", category: "academic", x: 465, y: 385 },
  { id: "sms", name: "School of Mechanical Sciences", short: "SMS", category: "academic", x: 465, y: 220 },
  { id: "smmme", name: "School of Minerals, Metallurgical and Materials Engineering", short: "SMMME", category: "academic", x: 420, y: 515 },
  { id: "lhc", name: "Lecture Hall Complex", short: "LHC", category: "academic", x: 285, y: 805 },
  { id: "mhr", name: "Mahanadi Hall of Residence", short: "MHR", category: "residential", x: 1010, y: 485 },
  { id: "bhr", name: "Brahmaputra Hall of Residence", short: "BHR", category: "residential", x: 1105, y: 485 },
  { id: "rhr", name: "Rushikulya Hall of Residence", short: "RHR", category: "residential", x: 1105, y: 355 },
  { id: "sac", name: "Student Activity Centre", short: "SAC", category: "student-life", x: 1035, y: 950 },
  { id: "community", name: "Community Centre", short: "COMMUNITY CENTRE", category: "student-life", x: 1180, y: 995 },
  { id: "sports", name: "Sports facilities / courts", short: "SPORTS COURTS", category: "sports", x: 1020, y: 825 },
  { id: "nescafe", name: "Nescafé (label on supplied road map)", short: "CAFÉ", category: "amenity", x: 900, y: 620 },
  { id: "overbridge", name: "Over Bridge", short: "OVER BRIDGE", category: "access", x: 800, y: 705 },
  { id: "jatni-gate", name: "Jatni Main Entrance Gate", short: "JATNI ENTRANCE", category: "access", x: 1020, y: 270 },
];
