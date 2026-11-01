# IIT Bhubaneswar Argul Campus — map research and assets

## Files
- `iitbbs-campus-map.svg` — editable vector map artwork.
- `iitbbs-campus-map.png` — 1920×1240 preview.
- `iitbbs-campus-map.html` — self-contained interactive preview; click markers and filter categories.
- `iitbbs-campus-map-data.json` — structured facility data, source/provenance notes, master-plan legend and limitations.

## Research findings used in the map

### Campus context
IIT Bhubaneswar's permanent campus is at Argul in Khordha district, Odisha, covers approximately 936 acres, and is described by the institute as being at the foot of Barunei Hill. The institute describes academic, residential, training-centre and research-park areas.

### Academic schools (current official naming)
1. School of Basic Sciences (SBS)
2. School of Earth, Ocean and Climate Sciences (SEOCS)
3. School of Electrical and Computer Sciences (SECS)
4. School of Humanities, Social Sciences and Management (SHSSM)
5. School of Infrastructure (SIF)
6. School of Mechanical Sciences (SMS)
7. School of Minerals, Metallurgical and Materials Engineering (SMMME)

The supplied older road map uses some legacy names/abbreviations: SES for School of Electrical Sciences and SHSS for Humanities/Social Sciences. The map uses current official names and keeps the source abbreviations understandable.

### Facilities documented by IIT Bhubaneswar
The official campus page lists Main Gate, Administrative Building, Academic Schools, Lecture Hall Complex, hostels, Guest House, Central Workshop, Central Research and Instrumentation Facility, First Year Laboratory Complex, Workshop Complex, quarters, auditoria, sports facilities, Commercial Complex, Gymkhana and Health Centre. The website also links to the Central Library and Sanjeevan Health Centre. The exact position of every item is not established by the two map graphics, so facilities without a defensible position are listed in the right panel rather than pinned.

Sports facilities named on the official campus page include table tennis, squash courts, volleyball courts, indoor badminton courts, hockey field, cricket field, basketball courts, athletics track, Student Activity Centre, football field and football stand building.

### Halls of Residence — source inconsistency
The official Hall of Residence overview says there are four halls (Ganga, Mahanadi, Brahmaputra and Subarnarekha), with about 2,000 capacity. The same page's contact list also includes Rushikulya Hall and Sangam Hall of Residence. The Students Life page has a different count and mentions A.N. Khosla Hall near the old academic campus in Bhubaneswar. Accordingly, the map lists six hall names from the official contact list but only pins MHR, BHR and RHR because those are the halls shown on the supplied Argul road-map graphic. Confirm exact current status/locations with the institute before relying on these details operationally.

### Master-plan categories
The supplied 2025 master-plan image uses five categories: existing building blocks, Phase III proposed building blocks, future academic building blocks, future residential/hostel blocks, and services. It also calls out net-zero energy, green infrastructure, rainwater harvesting, zero discharge and zero waste. The 2023 IIT Bhubaneswar PMC document contains an indicative master plan dated 11-09-2023 and labels existing infrastructure plus proposed roads, cycle tracks and buildings. It lists, among other items, Kendriya Vidyalaya, Research & Entrepreneurship Park, 600-seat boys'/girls' hostels, housing, a school extension, road/cycle-track works and water infrastructure. Those are planning references, not proof every project is complete today.

## Accuracy / limitations
- The drawn roads and labelled POI positions are diagrammatic translations of the user-supplied `ROAD MAP IIT BBS` illustration. No GPS or surveyed coordinates were present in the sources reviewed.
- The green organic background in the artwork is a decorative framing shape, not the IIT Bhubaneswar campus boundary.
- This is an orientation illustration, not a navigation, emergency-response or cadastral map. It is not to scale.
- The broader 2025 master-plan categories are included as a legend rather than traced as georeferenced polygons; doing so accurately would require a GIS/CAD source or a verified coordinate dataset.
- Nescafé and Community Centre are retained as labels from the supplied road map; their current operating status was not independently verified.
- The map does not place NetCoop's synthetic switches. No verified real switch positions, cabling paths or network topology for IIT Bhubaneswar were found in these campus sources. Keep the NetCoop synthetic topology as a separate overlay with an explicit `SIMULATED` label.

## Sources
- IIT Bhubaneswar, About Campus: https://www.iitbbs.ac.in/index.php/home/about-campus/
- IIT Bhubaneswar, Engineering Section / Master Plan: https://www.iitbbs.ac.in/index.php/home/engineering-section/
- IIT Bhubaneswar, How to Reach: https://www.iitbbs.ac.in/index.php/home/how-to-reach/
- IIT Bhubaneswar, Hall of Residence: https://www.iitbbs.ac.in/index.php/students-life-iitbbs/hall-of-residence/
- School of Electrical and Computer Sciences: https://secs.iitbbs.ac.in/
- School of Earth, Ocean and Climate Sciences: https://seocs.iitbbs.ac.in/
- IIT Bhubaneswar PMC RFP / Revised EOI (2023), Annexure XII: https://www.iitbbs.ac.in/wp-content/uploads/2023/12/Corrigendum_22122023.pdf
- IIT Bhubaneswar Annual Report 2021–22: https://www.iitbbs.ac.in/documents/IITBBSR_AR_2022_English.pdf
- User-supplied `ROAD MAP IIT BBS` and campus master-plan images.
