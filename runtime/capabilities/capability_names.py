from enum import Enum


class CapabilityName(str, Enum):
    GREETING = "greeting"
    SEARCH_PRODUCT = "search_product"
    SELECT_PRODUCT = "select_product"
    PRODUCT_DETAILS = "product_details"
    ADD_TO_CART = "add_to_cart"
    VIEW_CART = "view_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    UPDATE_CART_ITEM_QUANTITY = "update_cart_item_quantity"
    CLEAR_CART = "clear_cart"
    CHECKOUT = "checkout"
    COLLECT_DELIVERY_DETAILS = "collect_delivery_details"
    UPDATE_DELIVERY_DETAILS = "update_delivery_details"
    ABANDON_CHECKOUT = "abandon_checkout"
    CONFIRM_ORDER = "confirm_order"
    GET_ORDER_STATUS = "get_order_status"
    LIST_ORDERS = "list_orders"
    GET_ORDER_DETAILS = "get_order_details"
    CANCEL_ORDER = "cancel_order"
