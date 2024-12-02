# MegaLinter Flavor Generator

This script injects a new `bioinformatics` flavor into the MegaLinter code base, then builds and pushes that flavor as an image named `bl-megalinter`.

## Rationale

### Q: Why do any of this?
[MegaLinter](https://megalinter.io/latest/#why-megalinter) is great and super useful. Maintaining an equivalent tool takes a lot of effort and is brittle.

### Problem: The full flavor of MegaLinter is 9+ GB and takes 3+ minutes to download during a GitHub workflow.
Solution: Use a [flavor](https://megalinter.io/latest/flavors/) to reduce the image size.

### Problem: There are no flavors that contain [lintr](https://megalinter.io/latest/descriptors/r_lintr/) or [perlcritic](https://megalinter.io/latest/descriptors/perl_perlcritic/).
Solution: Request a new flavor that contains the linters we need.

### Problem: The MegaLinter devs have no obligation to accept our flavor or to make any updates we request in the future.
Solution: Fork MegaLinter or include it as a submodule.

### Q: Why not fork MegaLinter?
I tried that and ran into problems:
    * Adding a new flavor requires touching numerous files
    * MegaLinter has a _ton_ of specialized GitHub workflows, some of which are re-generated during the build
    * Maintaining local changes and attempting to sync with upstream changes is a _gigantic_ pain
    * _Not_ syncing with upstream (i.e. treating this as a one-off) will require us to start over if we want any changes


