from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout_view, name="checkout"),
    path("<uuid:id>/", views.order_detail_view, name="detail"),
]
