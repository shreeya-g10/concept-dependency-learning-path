# quiz_check_v2 replay on the ds101 review drafts

Working test on the questions that shaped the checks. Not an accuracy result.

Check model `llama3.1:8b`, prompt `quiz_check_v2`, temperature 0.0, seed 42, date 2026-11-03. Generated from `quiz_check_v2_replay_ds101.json`. Drafts: `quiz_v2`, 32 raw, 21 reached the second model.

★ marks the stored answer.

## avl_tree: What is the key property of an AVL tree that ensures efficient search operations?

- A `False` Each node has at most one red child
- B `False` Nodes are colored red and black
- C★ `True` The heights of the left and right subtrees differ by at most 1
- D `False` The tree is always perfectly balanced

Quote: AVL trees are height-balanced: At each node u, the height of the subtree rooted at u.left and the subtree rooted at u.right differ by at most one.

Quote proves: C. Same subject: True. About topic: True. **Final: keep**

## binary_search_tree: What is the binary search tree property in a BinarySearchTree?

- A `False` Every node stores a data value and the data values in both left and right subtrees are equal to the node’s value.
- B `True` Every node stores a data value and the data values in the left subtree are greater than or equal to the node’s value while the data values in the right subtree are less than or equal to the node’s value.
- C `False` Every node stores a data value and the data values in the left subtree are greater than the node’s value while the data values in the right subtree are less.
- D★ `True` Every node stores a data value and the data values in the left subtree are less than the node’s value while the data values in the right subtree are greater.

Quote: the data values in a binary search tree obey the binary search tree property: For a node, u, every data value stored in the subtree rooted at u.left is less than u.x and every data value stored in the subtree rooted at u.right is greater than u.x.

Quote proves: D. Same subject: True. About topic: True. **Final: drop** (check_several_true)

## binary_search_tree: What can happen to a BinarySearchTree?

- A★ `True` It can become unbalanced, leading to slower search times.
- B `False` It can only be used for storing strings.
- C `False` It can only have nodes with two children.
- D `False` It can only store numerical data values.

Quote: A BinarySearchTree is a special kind of binary tree in which each node, u, also stores a data value, u.x, from some total order. The data values in a binary search tree obey the binary search tree property: For a node, u, every data value stored in the subtree rooted at u.left is less than u.x and every data value stored in the subtree rooted at u.right is greater than u.x. An example of a BinarySearchTree is shown in Figure 6.5.

Quote proves: A. Same subject: True. About topic: True. **Final: keep**

## binary_search_tree: What is an example of a BinarySearchTree?

- A `False` A tree where nodes can have any number of children.
- B `False` A tree where nodes can have no children.
- C `False` A tree where nodes can have up to four children.
- D★ `True` A tree where nodes can have up to two children.

Quote: An example of a BinarySearchTree is shown in Figure 6.5.

Quote proves: D. Same subject: True. About topic: True. **Final: keep**

## binary_tree: What is the root node in a binary tree?

- A★ `True` A special node of degree at most two
- B `False` The node in the middle of the tree
- C `False` The node with the highest value
- D `False` The node with the lowest value

Quote: A special node, r, of degree at most two is called the root of the tree.

Quote proves: A. Same subject: True. About topic: True. **Final: keep**

## binary_tree: How are the children of a node in a binary tree typically distinguished?

- A `False` By their color
- B★ `True` By their position, left and right
- C `False` By their size
- D `False` By their value

Quote: Most of the binary trees we are interested in are ordered, so we distinguish between the left child and right child of u.

Quote proves: B. Same subject: True. About topic: True. **Final: keep**

## binary_tree: What is the maximum degree of any node in a binary tree?

- A `False` 1
- B `False` 2
- C★ `True` 3
- D `False` 4

Quote: and no vertex of degree greater than three

Quote proves: C. Same subject: True. About topic: True. **Final: keep**

## binary_tree: What is the height of a binary tree?

- A★ `True` The maximum depth of a node in the tree
- B `False` The number of edges in the tree
- C `False` The number of leaves in the tree
- D `False` The number of nodes in the tree

Quote: return 1 + max(height(u.left),height(u.right))

Quote proves: A. Same subject: True. About topic: True. **Final: keep**

## breadth_first_traversal: Why is an auxiliary boolean array used in the breadth-first traversal algorithm?

- A `False` to determine the shortest path
- B★ `True` to ensure vertices are not added to the queue more than once
- C `False` to keep track of the traversal path
- D `False` to store the traversal result

Quote: It does this by using an auxiliary boolean array, seen, that tracks which vertices have already been discovered.

Quote proves: B. Same subject: True. About topic: True. **Final: keep**

## breadth_first_traversal: What is the time complexity of the breadth-first traversal algorithm?

- A `False` O(m^2)
- B `False` O(n * m)
- C★ `True` O(n + m)
- D `False` O(n^2)

Quote: The entire algorithm runs in O(n + m) time.

Quote proves: C. Same subject: True. About topic: True. **Final: keep**

## graph: What is a graph in mathematics?

- A `True` A set of vertices and edges
- B `False` A set of vertices and edges where each edge is a single vertex
- C★ `True` A set of vertices and edges where each edge is an ordered pair of vertices
- D `False` A set of vertices and edges where each edge is an unordered pair of vertices

Quote: Mathematically, a (directed) graph is a pair G = (V ,E) where V is a set of vertices and E is a set of ordered pairs of vertices called edges.

Quote proves: C. Same subject: True. About topic: True. **Final: drop** (check_several_true)

## graph: What is an adjacency matrix used for in graph representation?

- A★ `True` To represent a graph by a matrix of boolean values
- B `False` To represent a graph by a matrix of color values
- C `False` To represent a graph by a matrix of numerical values
- D `False` To represent a graph by a matrix of string values

Quote: An adjacency matrix is a way of representing an n vertex graph G = (V ,E) by an n × n matrix, a, whose entries are boolean values.

Quote proves: A. Same subject: True. About topic: True. **Final: keep**

## queue: What is the main characteristic of a Queue data structure?

- A `False` Elements are added and removed from both ends
- B `False` Elements are added and removed from the middle
- C `True` Elements are added at the head and removed from the tail
- D★ `True` Elements are added at the tail and removed from the head

Quote: elements are removed (using the remove() operation) from the queue in the same order they are added (using the add(x) operation)

Quote proves: D. Same subject: True. About topic: True. **Final: drop** (check_several_true)

## queue: Why is an ArrayStack not a good choice for implementing a Queue?

- A `True` Because it can only add elements at the head
- B `True` Because it can only remove elements from the tail
- C `False` Because it has a fixed size
- D★ `False` Because it requires copying the entire array

Quote: This gives a running time proportional to n

Quote proves: B. Same subject: True. About topic: True. **Final: drop** (check_several_true)

## queue: What would make implementing a Queue easier?

- A `False` Using a linked list with a fixed size
- B `False` Using a stack with a fixed size
- C `False` Using an array with a fixed size
- D★ `True` Using an infinite array

Quote: The queue elements would always be stored in a[j],

Quote proves: D. Same subject: True. About topic: True. **Final: keep**

## rotation: What does rotation do in a red-black tree?

- A `False` It changes the color of nodes
- B `False` It merges nodes into one
- C★ `True` It rearranges nodes to maintain balance
- D `False` It splits nodes into two

Quote: The key to making the AVL tree work is to alter the insert and delete routines so as to maintain the balance property.

Quote proves: C. Same subject: True. About topic: True. **Final: keep**

## rotation: When might a rotation be needed in a red-black tree?

- A `False` After every insertion
- B `False` During a leaf addition
- C★ `True` When a node becomes unbalanced
- D `False` When the tree is fully balanced

Quote: For the bottommost unbalanced node, call it S, there are 4 cases

Quote proves: C. Same subject: True. About topic: True. **Final: keep**

## rotation: How does rotation affect the height of a red-black tree?

- A `False` It always decreases the height
- B `False` It always increases the height
- C★ `True` It can increase or decrease the height
- D `False` It does not affect the height

Quote: The ﬁrst and last node in this path are black and at most one out of every two internal nodes is red, so this path has at most log(n + 1) black nodes and at most log(n + 1) −1 red nodes.

Quote proves: NONE. Same subject: True. About topic: True. **Final: drop** (check_quote_no_proof)

## traversal: What is the first step in preorder traversal of a general tree?

- A `True` Visit the leftmost child
- B `False` Visit the right sibling
- C★ `False` Visit the root
- D `False` Visit the subtree

Quote: Preorder traversal of a general tree first visits the root of the tree

Quote proves: NONE. Same subject: True. About topic: True. **Final: drop** (check_disagrees)

## traversal: Why is inorder traversal not useful for general trees?

- A `False` Because it is too slow
- B `False` Because it only works for binary trees
- C `False` Because it requires too much memory
- D★ `True` Because there is no natural definition

Quote: Inorder traversal does not have a natural definition for the general tree, because there is no particular number of children for an internal node.

Quote proves: D. Same subject: True. About topic: True. **Final: keep**

## traversal: How does preorder traversal handle the children of a node?

- A★ `True` Visits them from left to right
- B `False` Visits them from right to left
- C `False` Visits them in a specific order based on their values
- D `False` Visits them randomly

Quote: This is accomplished by starting at R's leftmost child (call it T).

Quote proves: A. Same subject: True. About topic: True. **Final: keep**

## Dropped before the second model

- avl_tree: What is the maximum depth of an AVL tree with n nodes? (quote_not_in_book)
- avl_tree: How many cases are there for the bottommost unbalanced node after an insertion? (not_about_topic)
- avl_tree: What is the time complexity of insert and delete operations in an AVL tree? (quote_not_in_book)
- binary_search_tree: What is a potential problem with BinarySearchTrees? (near_duplicate)
- breadth_first_traversal: What is the primary data structure used to implement the queue in a breadth-first traversal? (no_source_quote)
- breadth_first_traversal: What is the order in which nodes are added to the queue during a breadth-first traversal starting from node 0? (quote_not_in_book)
- graph: What is a cycle in a graph? (quote_not_in_book)
- graph: What is the purpose of the seen array in the Breadth-First Search algorithm? (not_about_topic)
- queue: What is the main challenge in implementing an efficient ArrayQueue? (not_about_topic)
- rotation: What is the purpose of rotation in a red-black tree? (near_duplicate)
- traversal: What is the main difference between breadth-first search in graphs and trees? (not_about_topic)
