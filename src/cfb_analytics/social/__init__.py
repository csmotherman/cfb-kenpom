"""Draft-only social content generation for PRIME (rankings cards, and later
event-driven candidates). Every generator in this package only reads already
published PRIME data and only writes `social_posts` rows -- it never calls a
social platform. See docs in the architecture writeup for the publish-policy
gate that would allow that later.
"""
