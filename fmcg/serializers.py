# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import Product, FmcgRating, PickupAdress, FmcgOrder


class ProductSerializers(serializers.ModelSerializer):
    """Serializers for creating an FMCG product."""
    image_url = serializers.FileField(max_length=155)
    additional_images = serializers.FileField(max_length=155, required=False)
    subtitle = serializers.CharField(max_length=250, required=False)
    input_style = serializers.CharField(max_length=250, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "image_url",
            "name_and_size",
            "category",
            "price",
            "expiry_date",
            "description",
            "macro_nutrients",
            "micro_nutrients",
            "density",
            "calories",
            "moisture",
            "texture",
            "storage",
            "additional_images",
            "subtitle",
            "input_style",
        ]


class AddToCartSerializers(serializers.ModelSerializer):
    """Serializers for adding a product an FMCG product to cart."""

    class Meta:
        model = Product
        fields = [
            "id",
            "quantity"
        ]


class AddFmcgPickupAddressSerializers(serializers.ModelSerializer):
    class Meta:
        model = PickupAdress
        fields = [
            "name",
            "state"
        ]


class RetrieveCartProductsSerializers(serializers.Serializer):
    """Serializers for retrieving cart products."""
    message = serializers.CharField(max_length=200)


class RemoveFromCartSerializers(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class ProductOrderSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class FmcgOrderSerializer(serializers.ModelSerializer):
    products = ProductOrderSerializer(many=True)  # Accepts a list of products with IDs and quantities
    pin = serializers.CharField(max_length=4, min_length=4, required=False)
    use_biometrics = serializers.BooleanField(required=False)
    payment_method = serializers.CharField(max_length=50)
    available_addresses = serializers.CharField(max_length=50)

    class Meta:
        model = FmcgOrder
        fields = [
            "payment_method",
            "billing_address",
            "products",
            "delivery_address",
            "available_addresses",
            "total_price",
            "pin",
            "use_biometrics"
        ]

    def validate(self, data):
        billing_address = data.get("billing_address")

        # Validate required addresses based on billing address type
        if billing_address == "Store Pick-Up" and not data.get("available_addresses"):
            raise serializers.ValidationError({"available_addresses": "Available addresses are required for store pick-up."})
        elif billing_address == "Delivery" and not data.get("delivery_address"):
            raise serializers.ValidationError({"delivery_address": "Delivery address is required for delivery orders."})

        return data


class FmcgRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FmcgRating
        fields = [
            "id",
            "rating",
            "review",
        ]


class FmcgRatingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FmcgRating
        fields = [
            "id",
            "product",
            "rating",
            "review",
        ]


class PickupAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupAdress
        fields = ['name', 'state']
