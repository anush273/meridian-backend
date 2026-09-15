from meridian_backend.models.order import Order


class OrderService:
    def get_paid_orders(
        self,
        orders: list[Order],
    ) -> list[Order]:
        return [order for order in orders if order.status == "PAID"]

    def calculate_revenue(
        self,
        orders: list[Order],
    ) -> float:
        return sum(
            (order.total() for order in self.get_paid_orders(orders)),
            0.0,
        )

    def get_orders_by_customer(
        self,
        orders: list[Order],
        customer_id: int,
    ) -> list[Order]:
        return [order for order in orders if order.customer.id == customer_id]
    
    def get_highest_order(self, orders: list[Order]) -> Order:
        return max(orders, key=lambda order: order.total())


# orders: list[Order] = [
#     {
#         "id": 1,
#         "customer_id": 101,
#         "customer_name": "Anush",
#         "amount": 1200,
#         "status": "PAID",
#         "items": ["keyboard", "mouse"],
#     },
#     {
#         "id": 2,
#         "customer_id": 102,
#         "customer_name": "Rahul",
#         "amount": 700,
#         "status": "FAILED",
#         "items": ["headphones"],
#     },
#     {
#         "id": 3,
#         "customer_id": 103,
#         "customer_name": "Priya",
#         "amount": 2400,
#         "status": "PAID",
#         "items": ["monitor"],
#     },
#     {
#         "id": 4,
#         "customer_id": 101,
#         "customer_name": "Anush",
#         "amount": 1800,
#         "status": "PENDING",
#         "items": ["webcam"],
#     },
#     {
#         "id": 5,
#         "customer_id": 102,
#         "customer_name": "Rahul",
#         "amount": 3200,
#         "status": "PAID",
#         "items": ["laptop"],
#     },
# ]


# def get_paid_orders(orders: list[Order]):
#     paid_orders = [order for order in orders if order.get("status") == "PAID"]
#     return paid_orders


# def calculate_revenue(orders: list[Order]):
#     total_revenue = sum(order.get("amount", 0) for order in orders if order["status"] == "PAID")
#     return total_revenue


# def get_highest_value_order(orders: list[Order]):
#     value_of_orders = max(orders, key=lambda order: order.get("amount",0))
#     return value_of_orders


# def get_orders_by_customer(orders: list[Order], customer_id: int):
#     return [order for order in orders if order["customer_id"] == customer_id]


# def group_orders_by_status(orders: list[Order]):
#     status_order: dict[str, list[Order]] = {}
#     for order in orders:
#         status = order["status"]
#         if status not in status_order:
#             status_order[status] = []
#         status_order[status].append(order)
#     return status_order


# def get_unique_items(orders: list[Order]):
#     unique_items:set[str] = set()
#     for order in orders:
#         for item in order["items"]:
#             unique_items.add(item)
#     return unique_items


# def calculate_customer_spending(orders: list[Order]):
#     customer_spending: dict[str,int] = {}
#     for order in orders:
#         if order["status"] != "PAID":
#             continue
#         customer = order["customer_name"]
#         amount = order["amount"]

#         customer_spending[customer] = (
#             customer_spending.get(customer,0) + amount
#         )
#     return customer_spending
