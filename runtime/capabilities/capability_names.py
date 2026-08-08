from enum import Enum


class CapabilityName(str, Enum):
    GREETING = "greeting"
    SEARCH_PRODUCT = "search_product"
    SELECT_PRODUCT = "select_product"
    PRODUCT_DETAILS = "product_details"
    ADD_TO_CART = "add_to_cart"
    VIEW_CART = "view_cart"
    REMOVE_FROM_CART = "remove_from_cart"
