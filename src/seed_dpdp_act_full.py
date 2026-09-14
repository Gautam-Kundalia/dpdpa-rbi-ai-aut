"""
Seed db/dpdpa.db with the full Digital Personal Data Protection Act, 2023
— all 44 sections + the penalty Schedule.

Sources:
1. Act text: MeitY-hosted official copy of Act No. 22 of 2023 (assented
   11 Aug 2023): https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
2. Commencement dates: Gazette Notification G.S.R. 843(E), dated 13 Nov 2025
   (Ministry of Electronics and Information Technology), supplied by the
   user as an uploaded PDF (Timelines_for_enforcement_of_DPDPA.pdf).

Section 6 and Section 27 are each split into two rows because a specific
sub-clause of each commences on a different date than the rest of the
section (mirrors how Rule 8 was split in seed_dpdp_rules_full.py).

Usage:
    python src/init_db.py                 # schema only, if not already done
    python src/seed_dpdp_rules_full.py    # if not already run
    python src/seed_dpdp_act_full.py
    python src/export_word.py
    python src/export_excel.py
"""
from __future__ import annotations

import re

from db import PROJECT_ROOT, get_connection, init_schema

DOCX_PATH = "docs/DPDP_Act_2023.docx"

ACT_SOURCE_DOC = "Digital Personal Data Protection Act, 2023 (Act No. 22 of 2023)"
ACT_SOURCE_URL = "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf"
COMMENCEMENT_SOURCE_DOC = "Gazette Notification G.S.R. 843(E), 13 Nov 2025 (Act commencement schedule)"
COMMENCEMENT_SOURCE_URL = "user-upload:Timelines_for_enforcement_of_DPDPA.pdf"
FETCHED_DATE = "2026-08-31"

EFF_GROUP_A = ("2025-11-13", "In force from date of notification (G.S.R. 843(E), group (a)).")
EFF_GROUP_B = ("2026-11-13", "In force one year after notification (G.S.R. 843(E), group (b)).")
EFF_GROUP_C = ("2027-05-13", "In force eighteen months after notification (G.S.R. 843(E), group (c)) — not yet operative.")

# (provision_id, reference, topic, summary, effective_group, full_text)
PROVISIONS = [
    ("DPDPA-S1", "Section 1", "Other",
     "Short title of the Act and the commencement mechanism — different provisions can be brought into force on different notified dates, as happened via G.S.R. 843(E).",
     EFF_GROUP_A,
     "**Section 1 — Short title and commencement**\n\n"
     "(1) This Act may be called the Digital Personal Data Protection Act, 2023.\n\n"
     "(2) It shall come into force on such date as the Central Government may, by notification in the Official "
     "Gazette, appoint and different dates may be appointed for different provisions of this Act and any "
     "reference in any such provision to the commencement of this Act shall be construed as a reference to the "
     "coming into force of that provision."),

    ("DPDPA-S2", "Section 2", "Definitions",
     "Defines the Act's core terms — Data Fiduciary, Data Principal, Data Processor, Significant Data Fiduciary, personal data, processing, personal data breach, consent manager, Board, and more.",
     EFF_GROUP_A,
     "**Section 2 — Definitions**\n\n"
     "Key definitions (this tracker reproduces the terms most used elsewhere in it; consult the Act's full "
     "text for the complete list of 28 defined terms):\n\n"
     "(c) \"Board\" means the Data Protection Board of India established under section 18.\n\n"
     "(f) \"child\" means an individual who has not completed the age of eighteen years.\n\n"
     "(g) \"Consent Manager\" means a person registered with the Board, who acts as a single point of contact "
     "to enable a Data Principal to give, manage, review and withdraw her consent through an accessible, "
     "transparent and interoperable platform.\n\n"
     "(i) \"Data Fiduciary\" means any person who alone or in conjunction with other persons determines the "
     "purpose and means of processing of personal data.\n\n"
     "(j) \"Data Principal\" means the individual to whom the personal data relates and where such individual "
     "is — (i) a child, includes the parents or lawful guardian of such child; (ii) a person with disability, "
     "includes her lawful guardian, acting on her behalf.\n\n"
     "(k) \"Data Processor\" means any person who processes personal data on behalf of a Data Fiduciary.\n\n"
     "(l) \"Data Protection Officer\" means an individual appointed by the Significant Data Fiduciary under "
     "clause (a) of sub-section (2) of section 10.\n\n"
     "(t) \"personal data\" means any data about an individual who is identifiable by or in relation to such "
     "data.\n\n"
     "(u) \"personal data breach\" means any unauthorised processing of personal data or accidental disclosure, "
     "acquisition, sharing, use, alteration, destruction or loss of access to personal data, that compromises "
     "the confidentiality, integrity or availability of personal data.\n\n"
     "(x) \"processing\" in relation to personal data, means a wholly or partly automated operation or set of "
     "operations performed on digital personal data, and includes operations such as collection, recording, "
     "organisation, structuring, storage, adaptation, retrieval, use, alignment or combination, indexing, "
     "sharing, disclosure by transmission, dissemination or otherwise making available, restriction, erasure "
     "or destruction.\n\n"
     "(z) \"Significant Data Fiduciary\" means any Data Fiduciary or class of Data Fiduciaries notified by the "
     "Central Government under section 10."),

    ("DPDPA-S3", "Section 3", "Other",
     "Defines the territorial and material scope of the Act — applies to digital personal data processed in India, and to processing outside India connected to offering goods/services to people in India. Excludes purely personal/domestic processing and data the individual has made publicly available herself.",
     EFF_GROUP_C,
     "**Section 3 — Application of Act**\n\n"
     "Subject to the provisions of this Act, it shall —\n\n"
     "(a) apply to the processing of digital personal data within the territory of India where the personal "
     "data is collected —\n"
     "(i) in digital form; or\n"
     "(ii) in non-digital form and digitised subsequently;\n\n"
     "(b) also apply to processing of digital personal data outside the territory of India, if such processing "
     "is in connection with any activity related to offering of goods or services to Data Principals within "
     "the territory of India;\n\n"
     "(c) not apply to —\n"
     "(i) personal data processed by an individual for any personal or domestic purpose; and\n"
     "(ii) personal data that is made or caused to be made publicly available by —\n"
     "(A) the Data Principal to whom such personal data relates; or\n"
     "(B) any other person who is under an obligation under any law for the time being in force in India to "
     "make such personal data publicly available.\n\n"
     "**Illustration.** X, an individual, while blogging, publicly discloses her personal data. Such personal "
     "data is not protected under this Act."),

    ("DPDPA-S4", "Section 4", "Consent & Notice",
     "Personal data may only be processed for a lawful purpose (not expressly forbidden by law) where the Data Principal has given consent, or where one of the Act's 'certain legitimate uses' (Section 7) applies.",
     EFF_GROUP_C,
     "**Section 4 — Grounds for processing personal data**\n\n"
     "(1) A person may process the personal data of a Data Principal only in accordance with the provisions "
     "of this Act and for a lawful purpose —\n"
     "(a) for which the Data Principal has given her consent; or\n"
     "(b) for certain legitimate uses.\n\n"
     "(2) For the purposes of this section, \"lawful purpose\" means any purpose which is not expressly "
     "forbidden by law."),

    ("DPDPA-S5", "Section 5", "Consent & Notice",
     "Requires a notice (describing the personal data, purpose, and how to exercise rights or complain to the Board) to accompany or precede every consent request, and separately requires retrospective notice to people who consented before the Act's commencement.",
     EFF_GROUP_C,
     "**Section 5 — Notice**\n\n"
     "(1) Every request made to a Data Principal under section 6 for consent shall be accompanied or preceded "
     "by a notice given by the Data Fiduciary to the Data Principal, informing her —\n"
     "(i) the personal data and the purpose for which the same is proposed to be processed;\n"
     "(ii) the manner in which she may exercise her rights under sub-section (4) of section 6 and section 13; "
     "and\n"
     "(iii) the manner in which she may make a complaint to the Board,\n"
     "in such manner and as may be prescribed.\n\n"
     "(2) Where a Data Principal has given her consent to the processing of her personal data before the "
     "commencement of this Act, the Data Fiduciary shall, as soon as it is reasonably practicable, give to the "
     "Data Principal a notice informing her the information described in sub-section (1) in such manner as "
     "may be prescribed: Provided that the Data Fiduciary may continue to process the personal data of the "
     "Data Principal until and unless the Data Principal withdraws her consent.\n\n"
     "(3) The Data Fiduciary shall give the Data Principal the option to access the contents of the notice "
     "referred to in sub-section (1) or sub-section (2) in English or any language specified in the Eighth "
     "Schedule to the Constitution."),

    ("DPDPA-S6.1_8_10", "Section 6(1)-(8),(10)", "Consent & Notice",
     "Sets the standard for valid consent (free, specific, informed, unconditional, unambiguous, purpose-limited), the right to withdraw it at any time as easily as it was given, the consequences of withdrawal, and the Data Fiduciary's burden of proving valid notice/consent in any proceeding.",
     EFF_GROUP_C,
     "**Section 6(1)-(8),(10) — Consent**\n\n"
     "(1) The consent given by the Data Principal shall be free, specific, informed, unconditional and "
     "unambiguous with a clear affirmative action, and shall signify an agreement to the processing of her "
     "personal data for the specified purpose and be limited to such personal data as is necessary for such "
     "specified purpose.\n\n"
     "(2) Any part of consent referred to in sub-section (1) which constitutes an infringement of the "
     "provisions of this Act or the rules made thereunder or any other law for the time being in force shall "
     "be invalid to the extent of such infringement.\n\n"
     "(3) Every request for consent under the provisions of this Act shall be presented to the Data Principal "
     "in such manner that the same is clearly distinguishable, and shall be in clear and plain language, "
     "giving her the option to access such request in English or any language specified in the Eighth "
     "Schedule to the Constitution, and providing the contact details of a Data Protection Officer, where "
     "applicable, or any other person authorised by the Data Fiduciary to respond to any communication from "
     "her for the purpose of exercise of her rights under the provisions of this Act.\n\n"
     "(4) The Data Principal shall have the right to withdraw her consent at any time, with the ease of doing "
     "so being comparable to the ease with which such consent was given.\n\n"
     "(5) The consequences of the withdrawal referred to in sub-section (4) shall be borne by the Data "
     "Principal, and such withdrawal shall not affect the legality of processing of the personal data based on "
     "consent before its withdrawal.\n\n"
     "(6) In case of withdrawal of consent by the Data Principal pursuant to sub-section (4), the Data "
     "Fiduciary shall, within a reasonable time, cease and cause its Data Processors to cease processing the "
     "personal data of such Data Principal unless such processing without her consent is required or "
     "authorised under the provisions of this Act or any other law for the time being in force.\n\n"
     "(7) Consent given by the Data Principal may be managed, reviewed or withdrawn through a Consent "
     "Manager.\n\n"
     "(8) The Consent Manager shall be accountable to the Data Principal and shall act on her behalf.\n\n"
     "(10) In the event of any dispute arising from a claim made by a Data Principal that she did not receive "
     "a notice under section 5, or the request for consent under this section did not fulfil the requirements "
     "of this section, the burden of proof to show that notice was given by the Data Fiduciary in accordance "
     "with the provisions of this Act, or that the consent was validly given by the Data Principal to the Data "
     "Fiduciary in accordance with the provisions of this Act, as the case may be, shall lie on the Data "
     "Fiduciary."),

    ("DPDPA-S6.9", "Section 6(9)", "Consent Manager",
     "Every Consent Manager must be registered with the Board, subject to prescribed technical, operational, and financial conditions. (This sub-clause commences a year after the rest of Section 6, alongside Rule 4's registration process.)",
     EFF_GROUP_B,
     "**Section 6(9) — Registration of Consent Manager**\n\n"
     "Every Consent Manager shall be registered with the Board in such manner and subject to such technical, "
     "operational, financial and other conditions as may be prescribed.\n\n"
     "Operationalised by Rule 4 and the First Schedule of the DPDP Rules, 2025 (see DPDPR-R4, DPDPR-SCH1)."),

    ("DPDPA-S7", "Section 7", "Other",
     "Lists nine 'certain legitimate uses' that permit processing without consent — voluntary data-sharing for an obvious purpose, State benefit delivery, State legal functions, legal disclosure obligations, court orders, medical emergencies, public health measures, disaster response, and employment-related purposes.",
     EFF_GROUP_C,
     "**Section 7 — Certain legitimate uses**\n\n"
     "A Data Fiduciary may process personal data of a Data Principal for any of the following legitimate "
     "uses, namely —\n\n"
     "(a) for the specified purpose for which the Data Principal has voluntarily provided her personal data to "
     "the Data Fiduciary, and in respect of which she has not indicated to the Data Fiduciary that she does "
     "not consent to the use of her personal data;\n\n"
     "(b) for the State and any of its instrumentalities to provide or issue to the Data Principal such "
     "subsidy, benefit, service, certificate, licence or permit as may be prescribed, where —\n"
     "(i) she has previously consented to the processing of her personal data by the State or any of its "
     "instrumentalities for any subsidy, benefit, service, certificate, licence or permit; or\n"
     "(ii) such processing is in accordance with any policy formulated in accordance with any law for the time "
     "being in force, or any standards prescribed for that purpose;\n\n"
     "(c) for the performance by the State or any of its instrumentalities of any function under any law for "
     "the time being in force in India, or in the interest of sovereignty and integrity of India or security "
     "of the State, for that purpose;\n\n"
     "(d) for fulfilling any obligation under any law for the time being in force in India on any person to "
     "disclose any information to the State or any of its instrumentalities, subject to such processing being "
     "in accordance with the provisions regarding disclosure of such information in any other law for the "
     "time being in force;\n\n"
     "(e) for compliance with any judgment or decree or order issued under any law for the time being in "
     "force in India, or any judgment or order relating to claims of a contractual or civil nature under any "
     "law in force outside India;\n\n"
     "(f) for responding to a medical emergency involving a threat to the life or immediate threat to the "
     "health of the Data Principal or any other individual;\n\n"
     "(g) for taking measures to provide medical treatment or health services to any individual during an "
     "epidemic, outbreak of disease, or any other threat to public health;\n\n"
     "(h) for taking measures to ensure safety of, or provide assistance or services to, any individual during "
     "any disaster, or any breakdown of public order; or\n\n"
     "(i) for the purposes of employment or those related to safeguarding the employer from loss or liability, "
     "such as prevention of corporate espionage, maintenance of confidentiality of trade secrets, intellectual "
     "property, classified information or provision of any service to, or benefit sought by, Data Principal "
     "who is an employee."),

    ("DPDPA-S8", "Section 8", "Other",
     "Sets the Data Fiduciary's general obligations — responsibility regardless of contracts/Data Principal default, contractual requirement for engaging Data Processors, accuracy where decisions/disclosure are involved, security safeguards, breach intimation to the Board and Data Principals, erasure once purpose is no longer served, DPO/contact publication, and grievance redressal.",
     EFF_GROUP_C,
     "**Section 8 — General obligations of Data Fiduciary**\n\n"
     "(1) Irrespective of any agreement to the contrary or failure of a Data Principal to carry out the duties "
     "provided under this Act, the Data Fiduciary shall be responsible for complying with the provisions of "
     "this Act and the rules made thereunder in respect of any processing undertaken by it or on its behalf by "
     "a Data Processor.\n\n"
     "(2) A Data Fiduciary may engage, appoint, employ, or otherwise involve a Data Processor to process "
     "personal data on its behalf for any activity related to offering of goods or services to Data Principals "
     "only under a valid contract.\n\n"
     "(3) Where personal data of a Data Principal is likely to be used to make a decision that affects her, or "
     "is likely to be disclosed to another Data Fiduciary, the Data Fiduciary shall ensure the completeness, "
     "accuracy and consistency of personal data.\n\n"
     "(4) Where personal data of a Data Principal is likely to be processed for any purpose not related to "
     "sub-section (3), the Data Fiduciary shall implement appropriate technical and organisational measures to "
     "ensure effective observance of the provisions of this Act and the rules made thereunder.\n\n"
     "(5) The Data Fiduciary shall protect personal data in its possession or under its control, including in "
     "respect of any processing undertaken by it or on its behalf by a Data Processor, by taking reasonable "
     "security safeguards to prevent personal data breach.\n\n"
     "(6) In the event of a personal data breach, the Data Fiduciary shall give the Board and each affected "
     "Data Principal, intimation of such breach in such form and manner as may be prescribed.\n\n"
     "(7) The Data Fiduciary shall erase personal data, upon the Data Principal withdrawing her consent or as "
     "soon as it is reasonable to assume that the specified purpose is no longer being served, whichever is "
     "earlier, unless retention is necessary for compliance with any law for the time being in force, and "
     "cause its Data Processor to erase any personal data that was made available by the Data Fiduciary for "
     "processing to such Data Processor.\n\n"
     "(8) The purpose shall be deemed to no longer be served, if — (a) the Data Principal does not approach "
     "the Data Fiduciary for the performance of the specified purpose; and (b) exercise of any right of the "
     "Data Principal under the provisions of this Act in relation to such processing, for such period as may "
     "be prescribed, which may be different for different classes of Data Fiduciaries and the specified "
     "purposes.\n\n"
     "(9) The Data Fiduciary shall publish, in such manner as may be prescribed, the business contact "
     "information of a Data Protection Officer, if applicable, or any other person who is able to answer on "
     "behalf of the Data Fiduciary, the questions if any, raised by the Data Principal about the processing of "
     "her personal data.\n\n"
     "(10) The Data Fiduciary shall establish an effective mechanism to redress the grievances of Data "
     "Principals.\n\n"
     "(11) For the purpose of clause (b) of sub-section (8), the Data Principal shall be deemed to have not "
     "approached the Data Fiduciary for the performance of the specified purpose, or exercised her right in "
     "relation to her personal data processed by the Data Fiduciary, if she has not initiated any contact with "
     "the Data Fiduciary for such performance or exercise of her right in person, or over telephone, or "
     "through any visual or electronic means, or through a letter, or by initiating any proceeding under any "
     "law for the time being in force, during such period."),

    ("DPDPA-S9", "Section 9", "Children & Persons with Disabilities",
     "Requires verifiable parental/guardian consent before processing a child's (or disabled person's, where under lawful guardianship) personal data, bars processing likely to harm a child's wellbeing, and bars tracking/behavioural monitoring/targeted advertising directed at children — subject to prescribed exemptions and an age-based safe-harbour the government can notify.",
     EFF_GROUP_C,
     "**Section 9 — Processing of personal data of children**\n\n"
     "(1) The Data Fiduciary shall, before processing any personal data of a child or a person with disability "
     "who has a lawful guardian, obtain verifiable consent of the parent of the child or the lawful guardian, "
     "as the case may be, in such manner as may be prescribed.\n\n"
     "(2) The Data Fiduciary shall not undertake such processing of personal data that is likely to cause any "
     "detrimental effect on the well-being of a child.\n\n"
     "(3) The Data Fiduciary shall not undertake tracking or behavioural monitoring of children or targeted "
     "advertising directed at children.\n\n"
     "(4) The provisions of sub-sections (1) and (3) shall not apply to processing of personal data of a "
     "child by such class of Data Fiduciaries or for such purposes, and subject to such conditions, as may be "
     "prescribed.\n\n"
     "(5) The Central Government may notify the age above which the provisions of sub-sections (1) and (3) "
     "shall not apply, or apply to such extent as may be prescribed, to a Data Fiduciary or class of Data "
     "Fiduciaries, and the processing of personal data of a child by such Data Fiduciary or class of Data "
     "Fiduciaries is found by the Central Government to be verifiably safe, having regard to such factors as "
     "it may consider necessary."),

    ("DPDPA-S10", "Section 10", "Significant Data Fiduciary",
     "Empowers the government to designate Significant Data Fiduciaries based on data volume/sensitivity, rights risk, and sovereignty/security/electoral/public-order impact; requires them to appoint an India-based Data Protection Officer, an independent data auditor, and undertake periodic Data Protection Impact Assessments and audits.",
     EFF_GROUP_C,
     "**Section 10 — Additional obligations of Significant Data Fiduciary**\n\n"
     "(1) The Central Government may notify any Data Fiduciary or class of Data Fiduciaries as Significant "
     "Data Fiduciary, on the basis of an assessment of such relevant factors as it may determine, including —\n"
     "(a) the volume and sensitivity of personal data processed;\n"
     "(b) risk to the rights of Data Principal;\n"
     "(c) potential impact on the sovereignty and integrity of India;\n"
     "(d) risk to electoral democracy;\n"
     "(e) security of the State; and\n"
     "(f) public order.\n\n"
     "(2) The Significant Data Fiduciary shall —\n"
     "(a) appoint a Data Protection Officer who shall represent the Significant Data Fiduciary under the "
     "provisions of this Act and be based in India, who shall be responsible to the Board of Directors or "
     "similar governing body of the Significant Data Fiduciary, and shall be the point of contact for the "
     "grievance redressal mechanism referred to in the provisions of this Act;\n"
     "(b) appoint an independent data auditor to carry out the data audit, who shall evaluate the compliance "
     "of the Significant Data Fiduciary in accordance with the provisions of this Act; and\n"
     "(c) undertake the following measures, namely — (i) Data Protection Impact Assessment; (ii) periodic "
     "audit; and (iii) such other measures consistent with the provisions of this Act, as may be prescribed."),

    ("DPDPA-S11", "Section 11", "Data Principal Rights",
     "Gives a Data Principal the right to obtain a summary of her personal data being processed, the identities of other Data Fiduciaries/Processors it's been shared with, and other prescribed information — subject to a law-enforcement disclosure carve-out.",
     EFF_GROUP_C,
     "**Section 11 — Right to access information about personal data**\n\n"
     "(1) The Data Principal shall have the right to obtain from the Data Fiduciary to whom she has "
     "previously given consent to the processing of her personal data, subject to such requirements as may be "
     "prescribed —\n"
     "(a) a summary of personal data which is being processed by such Data Fiduciary and the processing "
     "activities undertaken by that Data Fiduciary with respect to such personal data;\n"
     "(b) the identities of all other Data Fiduciaries and Data Processors with whom the personal data has "
     "been shared by such Data Fiduciary, along with a description of the personal data so shared; and\n"
     "(c) any other information related to the personal data of such Data Principal and its processing, as "
     "may be prescribed.\n\n"
     "(2) The provisions of clauses (b) and (c) of sub-section (1) shall not apply if the sharing of personal "
     "data of the Data Principal by the Data Fiduciary to any other Data Fiduciary is in compliance with the "
     "provisions of this Act or any other law for the time being in force for the time being, for the purposes "
     "of prevention or detection or investigation of an offence or cyber incident, or for prosecution or "
     "punishment of offences, pursuant to any receipt of a request in this behalf pertaining to such sharing "
     "by any other Data Fiduciary."),

    ("DPDPA-S12", "Section 12", "Data Principal Rights",
     "Gives a Data Principal the right to correction, completion, updating, and erasure of her personal data (subject to legal retention requirements) for processing she previously consented to.",
     EFF_GROUP_C,
     "**Section 12 — Right to correction and erasure of personal data**\n\n"
     "(1) A Data Principal, who has given consent to the processing of her personal data under the provisions "
     "of this Act, shall have the right to correction, completion, updating and erasure of such personal data "
     "as may be applicable, in accordance with the requirements and in the manner as may be prescribed, for "
     "the processing of such personal data by such Data Fiduciary.\n\n"
     "(2) A Data Fiduciary shall, upon receiving a request for correction, completion or updating from a Data "
     "Principal under sub-section (1) —\n"
     "(a) correct the inaccurate or misleading personal data;\n"
     "(b) complete the incomplete personal data; and\n"
     "(c) update the personal data.\n\n"
     "(3) A Data Fiduciary shall, upon receiving a request for erasure of personal data from a Data Principal "
     "under sub-section (1), erase her personal data and cause its Data Processor to also erase such personal "
     "data that was made available by such Data Fiduciary for processing to such Data Processor, unless "
     "retention of the same is necessary for the specified purpose or compliance with any law for the time "
     "being in force."),

    ("DPDPA-S13", "Section 13", "Data Principal Rights",
     "Gives a Data Principal the right to readily available grievance redressal from the Data Fiduciary/Consent Manager, with a prescribed response period, and requires her to exhaust that route before approaching the Board.",
     EFF_GROUP_C,
     "**Section 13 — Right of grievance redressal**\n\n"
     "(1) A Data Principal shall have the right to have readily available means of grievance redressal "
     "provided by a Data Fiduciary or Consent Manager in respect of any act or omission of such Data Fiduciary "
     "or Consent Manager regarding the performance of its obligations in relation to the personal data of such "
     "Data Principal or the exercise of her rights under the provisions of this Act.\n\n"
     "(2) The Data Fiduciary or Consent Manager, as the case may be, shall respond to any grievance referred "
     "to in sub-section (1) within such period from the date of its receipt as may be prescribed.\n\n"
     "(3) A Data Principal shall exhaust the opportunity of redressal provided under sub-section (2) before "
     "approaching the Board."),

    ("DPDPA-S14", "Section 14", "Data Principal Rights",
     "Gives a Data Principal the right to nominate another individual to exercise her rights in the event of her death or incapacity.",
     EFF_GROUP_C,
     "**Section 14 — Right to nominate**\n\n"
     "(1) A Data Principal shall have the right to nominate, in such manner as may be prescribed, any other "
     "individual, who shall, in the event of death or incapacity of the Data Principal, exercise the rights of "
     "the Data Principal in accordance with the provisions of this Act and the rules made thereunder.\n\n"
     "(2) For the purposes of sub-section (1), \"incapacity\" means inability to exercise the rights of the "
     "Data Principal under this Act due to unsoundness of mind or infirmity of body."),

    ("DPDPA-S15", "Section 15", "Data Principal Rights",
     "Sets five duties on Data Principals — comply with applicable law, don't impersonate others, don't suppress material information on official documents, don't file false/frivolous grievances, and provide only verifiably authentic information when seeking correction/erasure.",
     EFF_GROUP_C,
     "**Section 15 — Duties of Data Principal**\n\n"
     "Every Data Principal shall — (a) comply with the provisions of all applicable laws for the time being "
     "in force while exercising rights under the provisions of this Act; (b) ensure not to impersonate "
     "another person while providing her personal data for a specified purpose; (c) ensure not to suppress "
     "any material information while providing her personal data for any document, unique identifier, proof "
     "of identity or proof of address issued by the State or any of its instrumentalities; (d) ensure not to "
     "register a false or frivolous grievance or complaint with a Data Fiduciary or the Board; and (e) furnish "
     "only such information as is verifiably authentic, while exercising the right to correction or erasure "
     "under the provisions of this Act or the rules made thereunder."),

    ("DPDPA-S16", "Section 16", "Cross-Border Transfer",
     "Allows the government to restrict transfer of personal data to specific notified countries/territories, without displacing any other law that provides stronger cross-border protection.",
     EFF_GROUP_C,
     "**Section 16 — Processing of personal data outside India**\n\n"
     "(1) The Central Government may, by notification, restrict the transfer of personal data by a Data "
     "Fiduciary for processing to such country or territory outside India as may be so notified.\n\n"
     "(2) Nothing contained in this section shall restrict the applicability of any law for the time being in "
     "force in India that provides for a higher degree of protection for or restriction on transfer of "
     "personal data by a Data Fiduciary outside India, of any personal data, to any person or any country "
     "outside India."),

    ("DPDPA-S17", "Section 17", "Exemptions",
     "Sets broad exemptions from most of the Act's obligations — for legal-right enforcement, judicial/regulatory processing, crime prevention/investigation, foreign-contract processing of non-Indian data, M&A restructuring, and defaulter financial-information processing — plus government-notified exemptions for security instrumentalities, research/statistics, and startups.",
     EFF_GROUP_C,
     "**Section 17 — Exemptions**\n\n"
     "(1) The provisions of Chapter II, except sub-sections (1) and (5) of section 8, and Chapter III shall "
     "not apply where — (a) processing of personal data is necessary for enforcing any legal right or claim; "
     "(b) processing of personal data by any court or tribunal or any other body in India which is entrusted "
     "by law with the performance of any judicial or quasi-judicial or regulatory or supervisory function, "
     "where such processing is necessary for the performance of such function; (c) processing of personal "
     "data is necessary for the purpose of prevention, detection, investigation or prosecution of any offence "
     "or contravention of any law for the time being in force in India; (d) processing of personal data of "
     "Data Principals not within the territory of India pursuant to any contract entered into with any person "
     "outside the territory of India, including any body corporate incorporated outside the territory of "
     "India, by any person based in India; (e) processing is necessary for a scheme of compromise or "
     "arrangement or merger or amalgamation of two or more companies or a reconstruction by way of "
     "demerger or otherwise of a company, or transfer of undertaking of one or more company to another company, "
     "or involving division of one or more companies, approved by a court, tribunal or other authority "
     "competent to do so by law; or (f) processing is for ascertaining the financial information and assets "
     "and liabilities of any person who has defaulted in payment due on account of a loan or advance taken "
     "from a financial institution, subject to such processing being in accordance with the provisions "
     "regarding disclosure of such information in any other law for the time being in force.\n\n"
     "(2) The provisions of this Act shall not apply in respect of the processing of personal data — (a) by "
     "such instrumentality of the State as the Central Government may notify, in the interest of sovereignty "
     "and integrity of India, security of the State, friendly relations with foreign States, maintenance of "
     "public order or preventing incitement to any cognizable offence relating to any of these, subject to "
     "such procedural safeguards as may be prescribed; and (b) necessary for research, archiving or "
     "statistical purposes if the personal data is not to be used to take any decision specific to a Data "
     "Principal and such processing is carried on in accordance with such standards as may be prescribed.\n\n"
     "(3) The Central Government may, before expiry of five years from the date of commencement of this Act, "
     "notify that any provision of this Act shall not apply to such class of Data Fiduciaries, including "
     "start-ups, for such period as may be specified in the notification, having regard to the volume and "
     "nature of personal data processed.\n\n"
     "(4) The provisions of sub-section (7) of section 8 and sub-section (3) of section 12, other than for "
     "the purposes referred to in clause (b) of sub-section (1) of this section, shall not apply in respect "
     "of processing by the State or any instrumentality of the State.\n\n"
     "(5) The Central Government may, by notification, exempt, from the application of provisions of this "
     "Act, the processing of personal data — (a) of Data Principals not within the territory of India; and "
     "(b) necessary for the purpose of research, archiving or statistical purposes, subject to such standards "
     "as may be prescribed."),

    ("DPDPA-S18", "Section 18", "Data Protection Board",
     "Establishes the Data Protection Board of India as a body corporate with perpetual succession, able to hold property and sue/be sued.",
     EFF_GROUP_A,
     "**Section 18 — Establishment of Board**\n\n"
     "(1) With effect from such date as the Central Government may, by notification, appoint, there shall be "
     "established, for the purposes of this Act, a Board to be called the Data Protection Board of India to "
     "exercise the powers conferred on, and perform the functions assigned to it, under this Act.\n\n"
     "(2) The Board shall be a body corporate by the name aforesaid having perpetual succession and a common "
     "seal, with power, subject to the provisions of this Act, to acquire, hold and dispose of property, both "
     "movable and immovable, and to contract, and shall, by the said name, sue or be sued.\n\n"
     "(3) The head office of the Board shall be at such place as the Central Government may notify."),

    ("DPDPA-S19", "Section 19", "Data Protection Board",
     "Sets the Board's composition (Chairperson + Members) and the qualification standard — ability, integrity, standing, and relevant expertise, with at least one legal expert.",
     EFF_GROUP_A,
     "**Section 19 — Composition and qualifications for appointment of Chairperson and Members**\n\n"
     "(1) The Board shall consist of a Chairperson and such number of other Members, as the Central "
     "Government may notify.\n\n"
     "(2) The Chairperson and other Members of the Board shall be appointed by the Central Government in "
     "such manner as may be prescribed.\n\n"
     "(3) The Chairperson and other Members of the Board shall be a person of ability, integrity and "
     "standing who has specialised knowledge or practical experience of not less than the prescribed period, "
     "in the areas including data governance, administration or implementation of laws related to data "
     "protection, dispute resolution, information and communication technology, digital economy, law, "
     "regulation or techno-regulation, or in any other field, which in the opinion of the Central Government, "
     "may be useful to the Board, and at least one of these members shall be an expert in the field of law."),

    ("DPDPA-S20", "Section 20", "Data Protection Board",
     "Sets Chairperson/Member salary and terms (prescribed by Rules — see Fifth Schedule) and a two-year, renewable term of office.",
     EFF_GROUP_A,
     "**Section 20 — Salary, allowances payable to and term of office of Chairperson and Members**\n\n"
     "(1) The salary and allowances payable to, and other terms and conditions of service of, the "
     "Chairperson and Members shall be such as may be prescribed and shall not be varied to their disadvantage "
     "after their appointment.\n\n"
     "(2) The Chairperson and each Member shall hold office for a term of two years from the date on which "
     "he enters upon his office, and shall be eligible for re-appointment."),

    ("DPDPA-S21", "Section 21", "Data Protection Board",
     "Lists disqualifications for Board appointment/continuation — insolvency, moral-turpitude conviction, incapacity, conflicting financial interest, or position abuse — and requires a hearing before removal.",
     EFF_GROUP_A,
     "**Section 21 — Disqualifications for appointment and continuation as Chairperson and Members of Board**\n\n"
     "(1) A person shall be disqualified for being appointed, or for continuing, as the Chairperson or a "
     "Member where he — (a) has been adjudged as an insolvent; (b) has been convicted of an offence which "
     "involves moral turpitude; (c) has become physically or mentally incapable of acting as such Chairperson "
     "or Member; (d) has acquired such financial or other interest as is likely to affect prejudicially his "
     "functions as such Chairperson or a Member; or (e) has so abused his position as to render his "
     "continuance in office prejudicial to the public interest.\n\n"
     "(2) No person referred to in sub-section (1) shall be removed from his office unless he has been given "
     "an opportunity of being heard in the matter."),

    ("DPDPA-S22", "Section 22", "Data Protection Board",
     "Sets the resignation process (effective on Government permission, three months' notice, successor appointment, or term expiry — whichever is earliest), vacancy-filling, and a one-year post-office employment restriction.",
     EFF_GROUP_A,
     "**Section 22 — Resignation by Members and filling of vacancy**\n\n"
     "(1) The Chairperson or any Member may, by notice in writing under his hand addressed to the Central "
     "Government, resign his office: Provided that the Chairperson or the Member shall continue to hold "
     "office until the expiry of three months from the date of receipt of such notice by the Central "
     "Government or until a person duly appointed as his successor enters upon his office or until the "
     "expiry of his term of office, whichever is earliest.\n\n"
     "(2) A vacancy caused by resignation or removal of the Chairperson or any Member, or by any other "
     "reason, shall be filled by fresh appointment.\n\n"
     "(3) The Chairperson or Member shall not, for a period of one year from the date of cessation of "
     "office, accept any employment in any organisation which has been a party to a proceeding before the "
     "Board under the provisions of this Act, without the prior approval of the Central Government: Provided "
     "that nothing contained in this sub-section shall apply where such employment is under the Central "
     "Government or a State Government, or in a Union territory, or a local authority, or in any statutory "
     "authority, or any corporation established by or under any Central, State or provincial Act, or a "
     "Government company as defined in clause (45) of section 2 of the Companies Act, 2013, subject to the "
     "condition that the Chairperson or the Member discloses such subsequent employment to the concerned "
     "organisation, where he has passed an order or issued a direction in relation to such organisation, "
     "under the provisions of this Act, during his term as such Chairperson or Member."),

    ("DPDPA-S23", "Section 23", "Data Protection Board",
     "Sets the Board's meeting/authentication procedure (prescribed by Rules — see Rule 19), and a savings clause protecting Board acts from invalidation due to vacancies, appointment defects, or non-material procedural irregularities.",
     EFF_GROUP_A,
     "**Section 23 — Proceedings of Board**\n\n"
     "(1) The Board shall meet at such times and places, and shall observe such procedure in regard to the "
     "transaction of business at its meetings, including by digital means, as may be prescribed, and the "
     "orders and directions of the Board shall be authenticated by the signature of the Chairperson or any "
     "other officer of the Board authorised by the Chairperson.\n\n"
     "(2) No act or proceeding of the Board shall be invalid merely by reason of — (a) any vacancy in, or any "
     "defect in the constitution of, the Board; or (b) any defect in the appointment of a person acting as "
     "the Chairperson or as a Member of the Board; or (c) any irregularity in the procedure of the Board not "
     "affecting the merits of the case.\n\n"
     "(3) If, for any reason, the Chairperson is unable to attend any meeting of the Board, the senior-most "
     "Member shall preside at the meeting and discharge the functions of the Chairperson till such time as "
     "the Chairperson resumes his office."),

    ("DPDPA-S24", "Section 24", "Data Protection Board",
     "Allows the Board, with prior Central Government approval, to appoint officers/employees necessary for its functions, on prescribed terms.",
     EFF_GROUP_A,
     "**Section 24 — Officers and employees of Board**\n\n"
     "The Board may, with the previous approval of the Central Government, appoint such officers and "
     "employees as it may consider necessary for the efficient discharge of its functions under this Act, and "
     "the salaries and allowances payable to, and other terms and conditions of service of, the officers and "
     "employees of the Board shall be such as may be prescribed."),

    ("DPDPA-S25", "Section 25", "Data Protection Board",
     "Deems the Chairperson, Members, officers, and employees of the Board to be public servants under the Indian Penal Code while acting under the Act.",
     EFF_GROUP_A,
     "**Section 25 — Members and officers of Board to be public servants**\n\n"
     "The Chairperson, Members, officers and employees of the Board shall be deemed, when acting or "
     "purporting to act in pursuance of any provisions of this Act, to be public servants within the meaning "
     "of section 21 of the Indian Penal Code."),

    ("DPDPA-S26", "Section 26", "Data Protection Board",
     "Gives the Chairperson general superintendence over Board administrative matters, and the power to delegate scrutiny/functions/proceedings to individual Members or groups of Members.",
     EFF_GROUP_A,
     "**Section 26 — Powers of Chairperson**\n\n"
     "(1) The Chairperson shall exercise such powers, as may be prescribed, of general superintendence and "
     "direction in respect of all administrative matters of the Board: Provided that the Chairperson may "
     "authorise any Member or officer of the Board to scrutinise any intimation, complaint, reference or "
     "direction received by the Board, in accordance with the provisions of this Act.\n\n"
     "(2) The Chairperson may authorise any Member or a group of Members to exercise such powers and perform "
     "such functions as may be prescribed and such Member or group of Members may exercise such powers and "
     "perform such functions, including conducting proceedings of the Board under this Act, subject to such "
     "conditions as may be specified in such authorisation.\n\n"
     "(3) The Chairperson may constitute Benches, as may be necessary, comprising one or more Members for "
     "exercise of the powers and performance of the functions of the Board and allocate the requisite items "
     "of work amongst such Benches."),

    ("DPDPA-S27.1a_c_e_2_3", "Section 27(1)(a)-(c),(e),(2),(3)", "Data Protection Board",
     "Sets most of the Board's core powers and functions — investigating breaches (on its own initiative, on complaints, or on government reference) and imposing penalties, issuing binding directions after a hearing, and modifying/withdrawing directions on representation.",
     EFF_GROUP_C,
     "**Section 27(1)(a)-(c),(e),(2),(3) — Powers and functions of Board**\n\n"
     "(1) The Board shall, on receipt of — (a) an intimation regarding a personal data breach under "
     "sub-section (6) of section 8, direct any urgent remedial or mitigation measures in the event of a "
     "personal data breach, inquire into such personal data breach and impose penalty as provided in this "
     "Act; (b) a complaint made by a Data Principal in respect of a breach in relation to her personal data, "
     "or the provisions of this Act, that is likely to affect the rights of Data Principals, or a reference "
     "made by the Central Government or a State Government, or in compliance of the directions of any Court, "
     "in relation to a breach in respect of provisions of this Act by a Data Fiduciary or Data Processor, "
     "inquire into such breach and impose penalty as provided in this Act; (c) a complaint against a Consent "
     "Manager registered under this Act, for breach of any of its obligations under this Act, inquire into "
     "such breach and impose penalty as provided in this Act; (e) any reference made by the Central "
     "Government under sub-section (2) of section 37, inquire into breach of provisions of that sub-section "
     "by an intermediary and impose penalty as provided in this Act.\n\n"
     "(2) The Board may, after making such inquiry as may be prescribed, issue such directions and take such "
     "action, as may be necessary, to any person for effective discharge of its functions under this Act, "
     "after giving such person an opportunity of being heard and for reasons to be recorded in writing.\n\n"
     "(3) The Board may, on receipt of a representation from a person affected by any direction issued under "
     "this section, or on receipt of a reference in this behalf from the Central Government or a State "
     "Government, and after giving such person and the Central Government or the State Government, as the "
     "case may be, an opportunity of being heard, modify, suspend, withdraw or cancel any direction issued "
     "under this section and while doing so, may impose any terms and conditions as it thinks fit."),

    ("DPDPA-S27.1d", "Section 27(1)(d)", "Consent Manager",
     "Gives the Board the power to inquire into, and penalise, a breach of Consent Manager registration conditions. (Commences a year after the rest of Section 27, alongside Section 6(9)'s Consent Manager registration requirement.)",
     EFF_GROUP_B,
     "**Section 27(1)(d) — Board's power over Consent Manager registration breaches**\n\n"
     "On receipt of an intimation of breach of any condition of registration referred to in sub-section (9) "
     "of section 6, the Board shall inquire into such breach and impose penalty as provided in this Act."),

    ("DPDPA-S28", "Section 28", "Data Protection Board",
     "Sets the Board's inquiry procedure as an independent, digital-by-design body — determining if grounds exist to proceed, natural-justice-based inquiries, civil-court-equivalent evidentiary powers, and the ability to close/warn/cost frivolous complaints.",
     EFF_GROUP_C,
     "**Section 28 — Procedure to be followed by Board**\n\n"
     "(1) The Board shall function as an independent body and, for the discharge of its functions under this "
     "Act, shall — (a) determine its own procedure for the conduct of its business, including the manner in "
     "which the Chairperson and its other Members shall discharge their business among themselves; (b) act as "
     "a digital office, with such design and in such manner as may be prescribed, to the extent possible, "
     "receiving complaints, documents through digital means and, for the purposes of inquiry, hearing the "
     "concerned parties through digital means, excepting situations where, for reasons to be recorded in "
     "writing, the Chairperson considers it necessary to summon in-person, any Data Principal, complainant, "
     "witness or any other concerned person for the just and proper disposal of the matter.\n\n"
     "(2) The Board shall, on receipt of any intimation of personal data breach under sub-section (6) of "
     "section 8 or complaint from a Data Principal or a reference from the Central Government or a State "
     "Government or a Court, or on receipt of a direction from the Appellate Tribunal in an appeal against any "
     "direction, decision or order of the Board, or on its own knowledge or information available to it, "
     "determine whether there exist sufficient grounds to proceed with an inquiry.\n\n"
     "(3) Where the Board finds that there does not exist sufficient grounds to proceed with the inquiry, it "
     "shall close proceedings and record reasons in writing.\n\n"
     "(4) Where the Board finds that there exists sufficient grounds to proceed with the inquiry, it shall "
     "conduct such inquiry in accordance with such procedure as may be prescribed, before making its "
     "decision.\n\n"
     "(5) No such inquiry as referred to in sub-section (4) shall be conducted unless the Board has served a "
     "notice on the Data Fiduciary or the Data Processor, if applicable, or the Consent Manager, as the case "
     "may be, calling upon it to justify as to why such an inquiry should not be initiated against it.\n\n"
     "(6) The Board shall, in relation to the discharge of its functions under this Act, follow the principle "
     "of natural justice.\n\n"
     "(7) The Board shall, for the purpose of discharging its functions under this Act, have the same powers "
     "as are vested in a civil court under the Code of Civil Procedure, 1908, while trying a suit, in respect "
     "of the following matters, namely: — (a) summoning and enforcing the attendance of any person and "
     "examining her on oath; (b) receiving evidence on affidavit; (c) subject to the provisions of sections "
     "123 and 124 of the Indian Evidence Act, 1872, requisitioning any public record or document or copy of "
     "such record or document from any office; (d) inspecting any data, book, document, register, books of "
     "account or any other document; (e) such other matters as may be prescribed.\n\n"
     "(8) The Board or any of its officers not below the rank of a Secretary to the Board, if authorised by "
     "the Board, shall not have the power to (a) block, or seize any premises, computer resource or other "
     "equipment used for or involved in the conduct of the day-to-day business or functions of a Data "
     "Fiduciary or Data Processor, or an intermediary; (b) require the disclosure of any information that is "
     "protected on the grounds of legal privilege.\n\n"
     "(9) The Board may, if it considers it necessary in the interest of justice, require the police or any "
     "officer of the Central Government or a State Government to render such assistance as may be necessary "
     "for discharge of its functions under this Act.\n\n"
     "(10) The Board may, at any time during the inquiry, if it considers necessary, by order, give such "
     "interim orders as it may think fit, after giving an opportunity of hearing to the person likely to be "
     "affected by such order.\n\n"
     "(11) The Board shall, after the conclusion of an inquiry initiated on the basis of information available "
     "to it, and after giving the concerned parties an opportunity of being heard, — (a) if satisfied that no "
     "breach of any of the provisions of this Act or the rules made thereunder has occurred, close the "
     "proceedings; or (b) if satisfied that breach of any provisions of this Act or the rules made thereunder "
     "by any person has occurred, proceed as per the provisions of section 33.\n\n"
     "(12) The Board may, if it is satisfied that a complaint is false or frivolous, issue a warning or impose "
     "costs on the complainant."),

    ("DPDPA-S29", "Section 29", "Data Protection Board",
     "Sets the appeal process to the Appellate Tribunal (the TRAI Appellate Tribunal, per the Act's definitions) against a Board order — 60-day filing window, extendable for sufficient cause, a 6-month target disposal timeline, and digital-by-design functioning.",
     EFF_GROUP_C,
     "**Section 29 — Appeal to Appellate Tribunal**\n\n"
     "(1) Any person aggrieved by an order or direction made by the Board under this Act may prefer an appeal "
     "before the Appellate Tribunal.\n\n"
     "(2) Every appeal made under sub-section (1) shall be filed within a period of sixty days from the date "
     "of receipt of the order or direction appealed against, in such form and manner and be accompanied by "
     "such fee as may be prescribed.\n\n"
     "(3) The Appellate Tribunal may entertain an appeal after the expiry of the said period of sixty days if "
     "it is satisfied that there was sufficient cause for not filing it within that period.\n\n"
     "(4) The Appellate Tribunal shall, after giving the parties to the appeal an opportunity of being heard, "
     "pass such orders thereon as it thinks fit, confirming, modifying or setting aside the order or direction "
     "appealed against.\n\n"
     "(5) The Appellate Tribunal shall send a copy of every order made by it to the Board and the parties to "
     "the appeal.\n\n"
     "(6) The appeal filed before the Appellate Tribunal under sub-section (1) shall be dealt with by it as "
     "expeditiously as possible and endeavour shall be made by it to dispose of the appeal within six months "
     "from the date of filing.\n\n"
     "(7) Where any appeal could not be disposed of within the period specified in sub-section (6), the "
     "Appellate Tribunal shall record its reasons in writing for not disposing of the appeal within the said "
     "period.\n\n"
     "(8) The Appellate Tribunal shall, for the purposes of adjudicating and deciding an appeal under this "
     "Act, exercise the same jurisdiction, powers and authority as it exercises under Section 18 of the "
     "Telecom Regulatory Authority of India Act, 1997.\n\n"
     "(9) An appeal against any order or decision of the Appellate Tribunal relating to any dispute regarding "
     "any direction, decision or order made under this Act shall lie to the Supreme Court in accordance with "
     "section 18B of the Telecom Regulatory Authority of India Act, 1997.\n\n"
     "(10) The Appellate Tribunal shall function as a digital office, and adopt techno-legal measures, to the "
     "extent possible, similar to the digital-office functioning of the Board under this Act."),

    ("DPDPA-S30", "Section 30", "Data Protection Board",
     "Makes Appellate Tribunal orders executable as a civil-court decree, either directly by the Tribunal or via transmission to a local civil court.",
     EFF_GROUP_C,
     "**Section 30 — Orders passed by Appellate Tribunal to be executable as a decree**\n\n"
     "(1) An order passed by the Appellate Tribunal under this Act shall be executable by it as a decree of "
     "civil court, and for this purpose, the Appellate Tribunal shall have all the powers of a civil court.\n\n"
     "(2) Notwithstanding anything contained in sub-section (1), the Appellate Tribunal may transmit any order "
     "made by it to a civil court having local jurisdiction and such civil court shall execute the order as if "
     "it were a decree made by that court."),

    ("DPDPA-S31", "Section 31", "Data Protection Board",
     "Allows the Board to direct parties toward mediation for disputes it considers suitable for that route.",
     EFF_GROUP_C,
     "**Section 31 — Alternate dispute resolution**\n\n"
     "Where the Board is of the opinion that any complaint may be resolved by mediation, it may direct the "
     "concerned parties to attempt resolution of the dispute through such mediator as the parties may mutually "
     "agree upon or as provided under any other law for the time being in force."),

    ("DPDPA-S32", "Section 32", "Data Protection Board",
     "Allows the Board to accept a voluntary undertaking from a person under inquiry (to take/refrain from action, or publicise the undertaking), which bars further proceedings on that matter unless the undertaking is later breached.",
     EFF_GROUP_C,
     "**Section 32 — Voluntary undertaking**\n\n"
     "(1) The Board may accept a voluntary undertaking in respect of any matter related to observance of the "
     "provisions of this Act, from any person, at any stage of a proceeding initiated under section 28 in "
     "respect of any matter related to observance of the provisions of this Act by such person.\n\n"
     "(2) An undertaking under sub-section (1) may include an undertaking to take such action, within such "
     "time, as may be determined by the Board, or refrain from taking such action, or to make good the loss "
     "caused to any Data Principal in the manner as agreed between the person and the Board, or to publicise "
     "such undertaking.\n\n"
     "(3) The terms and conditions of the undertaking may, on the request of the person or the Board, be "
     "varied if the Board is satisfied that circumstances warrant such a variation and the person agrees.\n\n"
     "(4) Upon acceptance of an undertaking by the Board, no further proceedings in respect of the matter "
     "covered by such undertaking shall be initiated or continued, as the case may be, against the person, "
     "and where such proceedings have already been initiated, no further steps shall be taken by the Board in "
     "such proceedings, except as provided under sub-section (5).\n\n"
     "(5) Where the Board is satisfied that the undertaking referred to in sub-section (1) has been breached, "
     "it may, for reasons to be recorded in writing, and after giving the person an opportunity of being "
     "heard, proceed with the matter covered in the undertaking as if the undertaking had not been accepted, "
     "and further, treat such breach as a breach of this Act and proceed as per the provisions of section 33."),

    ("DPDPA-S33", "Section 33", "Penalties",
     "Empowers the Board to impose the monetary penalties set out in the Schedule where it finds a significant breach, after a hearing, having regard to factors like breach severity, repetition, mitigation efforts, and proportionality.",
     EFF_GROUP_C,
     "**Section 33 — Penalties**\n\n"
     "(1) On being satisfied, after conducting an inquiry, that non-compliance by a person with any of the "
     "provisions of this Act or the rules made thereunder is significant, the Board may, after giving the "
     "person a reasonable opportunity of being heard, by order, impose such financial penalty specified in "
     "the Schedule as it may think fit.\n\n"
     "(2) The Board shall, before imposing any financial penalty under this section, have regard to the "
     "following matters, namely: — (a) nature, gravity and duration of the breach; (b) type and nature of the "
     "personal data affected by the breach; (c) repetitive nature of the breach; (d) whether the person, as a "
     "result of the breach, has realised a gain or avoided any loss; (e) whether the person took any action to "
     "mitigate the effects and consequences of the breach, and the timeliness and effectiveness of that "
     "action; (f) whether the financial penalty to be imposed is proportionate and effective, having regard to "
     "the need to secure observance of and deter breach of the provisions of this Act or the rules made "
     "thereunder; and (g) the likely impact of the imposition of the financial penalty on the person."),

    ("DPDPA-S34", "Section 34", "Penalties",
     "Requires all penalty sums realised by the Board to be credited to the Consolidated Fund of India.",
     EFF_GROUP_C,
     "**Section 34 — Crediting sums realised by way of penalties to Consolidated Fund of India**\n\n"
     "All sums realised by way of penalties imposed by the Board under this Act shall be credited to the "
     "Consolidated Fund of India."),

    ("DPDPA-S35", "Section 35", "Other",
     "Shields the Central Government, Board, and Board personnel from legal proceedings for anything done in good faith under the Act or Rules.",
     EFF_GROUP_A,
     "**Section 35 — Protection of action taken in good faith**\n\n"
     "No suit, prosecution or other legal proceedings shall lie against the Central Government, the Board, "
     "its Chairperson, or any Member, officer or employee thereof, for anything which is done or intended to "
     "be done in good faith under this Act or the rules made thereunder."),

    ("DPDPA-S36", "Section 36", "Other",
     "Empowers the Central Government to require the Board, or any Data Fiduciary/intermediary, to furnish information it calls for, for Act purposes.",
     EFF_GROUP_C,
     "**Section 36 — Power to call for information**\n\n"
     "The Central Government may, for the purposes of this Act, require the Board, or a Data Fiduciary, or "
     "an intermediary, as the case may be, to furnish such information as it may call for."),

    ("DPDPA-S37", "Section 37", "Other",
     "Empowers the Central Government to direct blocking of public access to a Data Fiduciary's online offering, after a hearing, where the Board has referred two or more monetary-penalty instances against that Data Fiduciary and recommends blocking in the public interest.",
     EFF_GROUP_C,
     "**Section 37 — Power of Central Government to issue directions**\n\n"
     "(1) The Central Government may, if satisfied that it is necessary or expedient so to do — (a) upon "
     "receipt of a reference from the Board in respect of its orders made under sub-section (1) of section 33 "
     "in respect of a Data Fiduciary, being made on two or more occasions; and (b) having regard to the "
     "reference, ascertained that it is necessary in the interest of the general public to block for access "
     "by the public or cause to be blocked for access by the public, any computer resource that enables such "
     "Data Fiduciary to offer any goods or services to Data Principals within the territory of India, direct "
     "any agency of the Central Government, after giving such Data Fiduciary an opportunity of being heard, "
     "to block for access by the public or cause to be blocked for access by the public any such computer "
     "resource, in such manner as provided in sub-section (2) of section 69A of the Information Technology "
     "Act, 2000.\n\n"
     "(2) Every intermediary shall, upon receipt of such order or direction as referred to in sub-section (1), "
     "cause such computer resource to be blocked, and thereupon the computer resource which has been directed "
     "to be blocked shall be blocked.\n\n"
     "(3) For the purposes of this section, the expressions \"computer resource\" and \"intermediary\" shall "
     "have the same meanings as respectively assigned to them in the Information Technology Act, 2000."),

    ("DPDPA-S38", "Section 38", "Other",
     "Clarifies the Act operates in addition to (not instead of) other laws, but prevails over any conflicting provision to the extent of the conflict.",
     EFF_GROUP_A,
     "**Section 38 — Consistency with other laws**\n\n"
     "(1) The provisions of this Act shall be in addition to, and not in derogation of, any other law for "
     "the time being in force.\n\n"
     "(2) In the event of any conflict between a provision of this Act and a provision of any other law for "
     "the time being in force, the provision of this Act shall prevail to the extent of such conflict."),

    ("DPDPA-S39", "Section 39", "Other",
     "Bars civil courts from hearing matters the Board is empowered to handle under the Act, and bars injunctions against actions taken under the Act's powers.",
     EFF_GROUP_A,
     "**Section 39 — Bar of jurisdiction**\n\n"
     "No civil court shall have jurisdiction to entertain any suit or proceeding in respect of any matter "
     "which the Board or the Appellate Tribunal is empowered to determine under the provisions of this Act, "
     "and no injunction shall be granted by any court or other authority in respect of any action taken or to "
     "be taken in pursuance of any power conferred by or under this Act."),

    ("DPDPA-S40", "Section 40", "Other",
     "The Central Government's rule-making power — this is the legal basis for the entire DPDP Rules, 2025, and lists 26 specific matters the Rules may cover.",
     EFF_GROUP_A,
     "**Section 40 — Power to make rules**\n\n"
     "(1) The Central Government may, by notification and subject to the condition of previous publication, "
     "make rules, not inconsistent with the provisions of this Act, generally to carry out the purposes of "
     "this Act.\n\n"
     "(2) In particular, and without prejudice to the generality of the foregoing power, such rules may "
     "provide for all or any of the following matters, namely: — (a) the manner of giving notice under "
     "sub-sections (1) and (2) of section 5; (b) the manner in which the Consent Manager shall be accountable "
     "to the Data Principal, and its other obligations, under sub-section (8) of section 6; (c) the manner of "
     "registration and the technical, operational, financial and other conditions for registration of the "
     "Consent Manager under sub-section (9) of section 6; (d) any subsidy, benefit, service, certificate, "
     "licence or permit for the purpose of clause (b) of section 7; (e) the form and manner of intimation of "
     "personal data breach to the Board and each affected Data Principal under sub-section (6) of section 8; "
     "(f) the time period for the purpose of clause (b) of sub-section (8) of section 8; (g) the manner of "
     "publishing the business contact information of a Data Protection Officer or any person under sub-section "
     "(9) of section 8; (h) the manner of obtaining consent from parent or lawful guardian for processing of "
     "personal data of a child or of a person with disability who has a lawful guardian under sub-section (1) "
     "of section 9; (i) the class of Data Fiduciaries and the purposes for processing of personal data of a "
     "child under sub-section (4) of section 9; (j) the manner in which a Significant Data Fiduciary shall "
     "conduct Data Protection Impact Assessment and audit under sub-clause (i) of clause (c) of sub-section "
     "(2) of section 10; (k) the other measures consistent with the provisions of this Act to be undertaken "
     "by a Significant Data Fiduciary under sub-clause (iii) of clause (c) of sub-section (2) of section 10; "
     "(l) the requirements subject to which and the manner in which the Data Principal may obtain information "
     "from and make a request to the Data Fiduciary under sub-section (1) of section 11; (m) the requirements "
     "and manner for correction, completion, updating and erasure of personal data of the Data Principal for "
     "the processing of such personal data under sub-section (1) of section 12; (n) the period within which "
     "the Data Fiduciary or Consent Manager shall respond to any grievance under sub-section (2) of section "
     "13; (o) the manner of nomination of any other individual by the Data Principal under sub-section (1) of "
     "section 14; (p) the standard subject to which the processing of personal data may be done for research, "
     "archiving or statistical purposes under clause (b) of sub-section (2) of section 17; (q) the manner of "
     "appointment of the Chairperson and other Members of the Board under sub-section (2) of section 19; "
     "(r) the salary and allowances payable to, and other terms and conditions of service of, the Chairperson "
     "and Members under sub-section (1) of section 20; (s) the manner of authentication of orders and "
     "directions of the Board under sub-section (1) of section 23; (t) the salary and allowances payable to, "
     "and other terms and conditions of service of, the officers and employees of the Board under section 24; "
     "(u) the manner in which the Board shall function as a digital office and adopt techno-legal measures "
     "under clause (b) of sub-section (1) of section 28; (v) other matters in respect of which the Board shall "
     "have same powers as vested in a civil court under sub-clause (e) of clause (7) of section 28; (w) the "
     "form, manner and fee for filing an appeal under sub-section (2) of section 29; (x) any other matter "
     "which is required to be, or may be, prescribed or in respect of which provision is to be made by rules.\n\n"
     "This is the legal basis for the DPDP Rules, 2025 as a whole (see DPDPR-* provisions)."),

    ("DPDPA-S41", "Section 41", "Other",
     "Requires every rule and certain notifications (under Sections 16 and 42) to be laid before both Houses of Parliament for a 30-day review period, during which Parliament can modify or annul them.",
     EFF_GROUP_A,
     "**Section 41 — Laying of rules and certain notifications**\n\n"
     "Every rule made under this Act and every notification issued under section 16 and section 42 shall be "
     "laid, as soon as may be after it is made or issued, before each House of Parliament, while it is in "
     "session, for a total period of thirty days which may be comprised in one session or in two or more "
     "successive sessions, and if, before the expiry of the session immediately following the session or the "
     "successive sessions aforesaid, both Houses agree in making any modification in the rule or notification "
     "or both Houses agree that the rule or notification should not be made or issued, the rule or "
     "notification shall thereafter have effect only in such modified form or be of no effect, as the case "
     "may be; so, however, that any such modification or annulment shall be without prejudice to the "
     "validity of anything previously done under that rule or notification."),

    ("DPDPA-S42", "Section 42", "Penalties",
     "Allows the Central Government to amend the penalty Schedule by notification, capped at no more than double the originally enacted penalty amounts; amendments take effect as if enacted, from the notification date.",
     EFF_GROUP_A,
     "**Section 42 — Power to amend Schedule**\n\n"
     "(1) The Central Government may, by notification, amend the Schedule so, however, that the amount "
     "specified therein in respect of any breach shall not, in aggregate, exceed two hundred and fifty crore "
     "rupees at any given time, and every such notification shall be laid before each House of Parliament.\n\n"
     "(2) Any amendment notified under sub-section (1) shall have effect as if enacted in this Act and shall "
     "come into force on the date of the notification."),

    ("DPDPA-S43", "Section 43", "Other",
     "A standard 'removal of difficulties' clause — allows the government to make necessary orders to resolve implementation difficulties, but only within three years of the Act's commencement, and such orders must be laid before Parliament.",
     EFF_GROUP_A,
     "**Section 43 — Power to remove difficulties**\n\n"
     "(1) If any difficulty arises in giving effect to the provisions of this Act, the Central Government "
     "may, by order published in the Official Gazette, make such provisions, not inconsistent with the "
     "provisions of this Act, as may appear to be necessary for removing the difficulty: Provided that no "
     "such order shall be made after the expiry of a period of three years from the date of commencement of "
     "this Act.\n\n"
     "(2) Every order made under this section shall be laid, as soon as may be after it is made, before each "
     "House of Parliament."),

    ("DPDPA-S44.1_3", "Section 44(1),(3)", "Other",
     "Amends the TRAI Act, 1997 to fold in the DPDP Appellate Tribunal, and amends the RTI Act, 2005 to redefine what counts as exempt 'personal information' by reference to this Act.",
     EFF_GROUP_A,
     "**Section 44(1),(3) — Amendments to certain Acts**\n\n"
     "(1) In the Telecom Regulatory Authority of India Act, 1997, in section 14, in clause (c), after "
     "sub-clause (ii), the following sub-clause shall be inserted, namely — \"(iii) the Digital Personal Data "
     "Protection Act, 2023;\".\n\n"
     "(3) In the Right to Information Act, 2005, in section 8, in sub-section (1), for clause (j), the "
     "following clause shall be substituted, namely — \"(j) information which relates to personal "
     "information;\"."),

    ("DPDPA-S44.2", "Section 44(2)", "Other",
     "Amends the Information Technology Act, 2000 — removes the old compensation-for-data-breach provision (Section 43A, since this Act now governs that), and cross-references this Act in two other IT Act provisions.",
     EFF_GROUP_C,
     "**Section 44(2) — Amendments to the Information Technology Act, 2000**\n\n"
     "In the Information Technology Act, 2000, — (a) section 43A shall be omitted; (b) in section 81, in the "
     "proviso, for the words \"the Patents Act, 1970\", the words \"the Patents Act, 1970 and the Digital "
     "Personal Data Protection Act, 2023\" shall be substituted; (c) in section 87, in sub-section (2), clause "
     "(ob) shall be omitted."),

    ("DPDPA-SCHED", "Schedule (Act)", "Penalties",
     "Sets the monetary penalty ranges the Board can impose for different categories of breach — up to ₹250 crore for a security-safeguard breach, ₹200 crore for breach-notification or children's-data failures, ₹150 crore for Significant Data Fiduciary obligation breaches, and ₹50 crore for other breaches of the Act or Rules.",
     EFF_GROUP_C,
     "**Schedule** *(see sub-section (1) of section 33)*\n\n"
     "| Nature of breach | Penalty (may extend to) |\n"
     "|---|---|\n"
     "| Breach in observing the obligation of Data Fiduciary to take reasonable security safeguards to "
     "prevent personal data breach under sub-section (5) of section 8. | Two hundred and fifty crore rupees. |\n"
     "| Breach in observance of the obligation to notify the Board and affected Data Principals of a personal "
     "data breach under sub-section (6) of section 8. | Two hundred crore rupees. |\n"
     "| Breach in observance of additional obligations in relation to children under section 9. | Two hundred "
     "crore rupees. |\n"
     "| Breach in observance of additional obligations of Significant Data Fiduciary under section 10. | One "
     "hundred and fifty crore rupees. |\n"
     "| Breach in observance of the duties under section 15. | Ten thousand rupees. |\n"
     "| Breach of any term of voluntary undertaking accepted by the Board under section 32. | Extendable up to "
     "the limit applicable to the breach in respect of which the proceedings under section 28 were instituted. |\n"
     "| Breach of any other provision of this Act or the rules made thereunder. | Fifty crore rupees. |"),
]

CHANGE_TYPE = "New Provision"
DETECTED_BY = "manual-seed:gazette-import"
CONFIDENCE = 0.97


def make_anchor(provision_id: str) -> str:
    """Word bookmark names: letters/digits/underscores only, must start with a letter."""
    anchor = re.sub(r"[^A-Za-z0-9_]", "_", provision_id)
    if not anchor[0].isalpha():
        anchor = "P_" + anchor
    return anchor[:40]


def build_provision_row(pid, ref, topic, summary, eff_group, full_text, idx):
    eff_date, eff_note = eff_group
    change_id = f"CHG-A{idx:04d}"
    instrument_type = "Schedule" if ref.startswith("Schedule") else "Act Section"
    return {
        "provision_id": pid,
        "instrument_type": instrument_type,
        "reference": ref,
        "topic_category": topic,
        "current_summary": summary,
        "full_text": full_text,
        "full_text_path": DOCX_PATH,
        "full_text_anchor": make_anchor(pid),
        "sort_order": idx,
        "status": "Active",
        "effective_date": eff_date,
        "last_updated_date": FETCHED_DATE,
        "source_document": ACT_SOURCE_DOC,
        "source_url": ACT_SOURCE_URL,
        "confidence_score": CONFIDENCE,
        "review_status": "Pending Review",
        "reviewed_by": None,
        "review_date": None,
        "latest_change_id": change_id,
        "notes": eff_note if eff_date > FETCHED_DATE else "Currently in force.",
    }, change_id, eff_note


def build_change_row(change_id, pid, summary, full_text, eff_note):
    return {
        "change_id": change_id,
        "detected_timestamp": f"{FETCHED_DATE} 00:00",
        "provision_id": pid,
        "change_type": CHANGE_TYPE,
        "old_value_summary": None,
        "new_value_summary": summary,
        "old_full_text": None,
        "new_full_text": full_text,
        "source_document": ACT_SOURCE_DOC,
        "source_url": ACT_SOURCE_URL,
        "detected_by": DETECTED_BY,
        "confidence_score": CONFIDENCE,
        "review_status": "Pending Review",
        "reviewed_by": None,
        "review_date": None,
        "applied_to_master": "Y",
        "notes": f"Initial baseline load from Act text; commencement per G.S.R. 843(E). {eff_note}",
    }


def main():
    DB_PATH = PROJECT_ROOT / "db" / "dpdpa.db"
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_schema(conn)

    prov_cols = None
    change_cols = None
    n = 0

    for i, (pid, ref, topic, summary, eff_group, full_text) in enumerate(PROVISIONS, start=1):
        prov_row, change_id, eff_note = build_provision_row(pid, ref, topic, summary, eff_group, full_text, i)
        change_row = build_change_row(change_id, pid, summary, full_text, eff_note)

        if prov_cols is None:
            prov_cols = list(prov_row.keys())
        if change_cols is None:
            change_cols = list(change_row.keys())

        conn.execute(
            f"INSERT OR REPLACE INTO provisions ({','.join(prov_cols)}) "
            f"VALUES ({','.join('?' for _ in prov_cols)})",
            [prov_row[c] for c in prov_cols],
        )
        conn.execute(
            f"INSERT OR REPLACE INTO change_log ({','.join(change_cols)}) "
            f"VALUES ({','.join('?' for _ in change_cols)})",
            [change_row[c] for c in change_cols],
        )
        n += 1

    source_rows = [
        {
            "document_id": "SRC-0002",
            "source": "MeitY",
            "title": ACT_SOURCE_DOC,
            "url": ACT_SOURCE_URL,
            "published_date": "2023-08-11",
            "fetched_date": FETCHED_DATE,
            "content_hash": "manual-seed-not-hashed",
            "processing_status": "Processed",
            "linked_change_ids": ",".join(f"CHG-A{i:04d}" for i in range(1, n + 1)),
        },
        {
            "document_id": "SRC-0003",
            "source": "eGazette",
            "title": COMMENCEMENT_SOURCE_DOC,
            "url": COMMENCEMENT_SOURCE_URL,
            "published_date": "2025-11-13",
            "fetched_date": FETCHED_DATE,
            "content_hash": "manual-seed-not-hashed",
            "processing_status": "Processed",
            "linked_change_ids": ",".join(f"CHG-A{i:04d}" for i in range(1, n + 1)),
        },
    ]
    for source_row in source_rows:
        conn.execute(
            f"INSERT OR REPLACE INTO source_log ({','.join(source_row)}) "
            f"VALUES ({','.join('?' for _ in source_row)})",
            list(source_row.values()),
        )

    conn.commit()
    conn.close()
    print(f"Loaded {n} Act provisions (verbatim) and {n} change_log rows.")


if __name__ == "__main__":
    main()
