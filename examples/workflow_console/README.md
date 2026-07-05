# Workflow Console Examples

This folder contains path-independent example Work templates for the local
NiceGUI Workflow Console.

Use the console's New Workspace dialog and enable `Include example Works` to
copy these examples into the selected workspace. The examples are static
workflow artifacts only: they do not call a provider, run CAD generation, create
assemblies, or write outside the chosen workspace.

The MVP examples cover:

- `single_part_mounting_plate`: a single-part Work with a successful root run.
- `multi_part_enclosure_planning`: a multi-part planning Work with base, lid,
  and screws in the Parts Matrix.
- `reviewed_one_part_enclosure_base`: a multi-part Work where one selected
  part has a reviewed single-part result.
