"""Source acquisition and ingestion (backend M3).

Downloads keep the original bytes unmodified (stored by SHA-256) and produce a ``SourceArtifact``
manifest. Parsers turn verified source formats into records with provenance pointing back at the
artifact. Network access is only needed to *acquire*; everything else works offline.
"""
