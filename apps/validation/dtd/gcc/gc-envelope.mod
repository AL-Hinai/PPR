<!--
In the eCTD File Organisation: "util/dtd/gc-envelope.mod"

Version 1.2
Oct 2015

PPR note: transcribed from Appendix 6 of the GCC Module 1 Specifications v1.5.
-->

<!-- ................................................................... -->
<!ELEMENT gc-envelope (
 envelope+
)>

<!ELEMENT envelope (
 application,
 applicant,
 agency,
 atc*,
 submission,
 submission-unit,
 procedure,
 invented-name+,
 inn*,
 sequence,
 related-sequence*,
 submission-description
)>

<!-- ................................................................... -->
<!ELEMENT application    ( number* )>
<!ELEMENT applicant      ( #PCDATA )>
<!ELEMENT agency     EMPTY>
<!ELEMENT atc     ( #PCDATA )>
<!ELEMENT submission      EMPTY>
<!ELEMENT submission-unit   EMPTY>
<!ELEMENT procedure       EMPTY>
<!ELEMENT invented-name    ( #PCDATA )>
<!ELEMENT inn     ( #PCDATA )>
<!ELEMENT sequence    ( #PCDATA )>
<!ELEMENT related-sequence   ( #PCDATA )>
<!ELEMENT submission-description  ( #PCDATA )>
<!ELEMENT number     ( #PCDATA )>

<!-- ................................................................... -->
<!ATTLIST agency code (
  AE-MOH
| BH-MOH
| KW-MOH
| OM-MOH
| QA-NHA
| SA-SFDA
| YE-MOPHP
) #REQUIRED>

<!-- ................................................................... -->
<!ATTLIST procedure type (
   gcc
 | national
 ) #REQUIRED>

<!-- ................................................................... -->
<!ATTLIST submission type (
  asmf
| extension
| new-gen
| new-nce
| new-bio
| new-rad
| none
| pmf
| psur
| psusa
| renewal
| rmp
| transfer-ma
| usr
| var-type1
| var-type2
| withdrawal
) #REQUIRED>

<!-- ................................................................... -->
<!ATTLIST submission-unit type (
  initial
| response
| additional-info
| closing
| correction
| reformat
) #REQUIRED>

<!-- ................................................................... -->
<!ENTITY % env-countries "(ae|common|bh|kw|om|qa|sa|ye)">

<!-- ................................................................... -->
<!ATTLIST envelope country %env-countries; #REQUIRED >

<!-- +++ -->
