<!-- Source: OpenDSA (opendsa.org), commit f900a7a, RST/en/SearchStruct/AVL.rst. MIT License, Copyright (c) 2011-2025 Ville Karavirta and Cliff Shaffer. Converted to Markdown; directives, figures, visualizations and code removed. See data/raw/README.md. -->

# The AVL Tree

The AVL tree (named for its inventors Adelson-Velskii and Landis)
should be viewed as a BST with the following additional property:
For every node, the heights of its left and right subtrees differ by
at most 1.
As long as the tree maintains this property, if the tree contains
n nodes, then it has a depth of at most O(\log n).
As a result, search for any node will cost O(\log n),
and if the updates can be done in time proportional to the depth of
the node inserted or deleted, then updates will also cost
O(\log n), even in the worst case.

The key to making the AVL tree work is to alter the insert and delete
routines so as to maintain the balance property.
Of course, to be practical, we must be able to implement the revised
update routines in \Theta(\log n) time.

Consider what happens when we insert a node with key value 5,
as shown in the figure.
The tree on the left meets the AVL tree balance requirements.
After the insertion, two nodes no longer meet the requirements.
Because the original tree met the balance requirement, nodes in the
new tree can only be unbalanced by a difference of at most 2 in the
subtrees.
For the bottommost unbalanced node, call it S, there are 4
cases:

- The extra node is in the left child of the left child of
S.
- The extra node is in the right child of the left child of
S.
- The extra node is in the left child of the right child of
S.
- The extra node is in the right child of the right child of
S.

Cases 1 and 4 are symmetrical, as are cases 2 and 3.
Note also that the unbalanced nodes must be on the path from
the root to the newly inserted node.

Our problem now is how to balance the tree in O(\log n) time.
It turns out that we can do this using a series of local operations
known as rotations.
Cases 1 and 4 can be fixed using a single rotation,
as shown in the figure.
Cases 2 and 3 can be fixed using a double rotation, as shown
in the figure.

The AVL tree insert algorithm begins with a normal BST insert.
Then as the recursion unwinds up the tree, we perform the appropriate
rotation on any node that is found to be unbalanced.
Deletion is similar; however, consideration for unbalanced nodes must
begin at the level of the `deletemin` operation.

In the figure (b), the bottom-most unbalanced
node has value 7.
The excess node (with value 5) is in the right subtree of the left
child of 7, so we have an example of Case 2.
This requires a double rotation to fix.
After the rotation, 5 becomes the left child of 24, 2 becomes the
left child of 5, and 7 becomes the right child of 5.
