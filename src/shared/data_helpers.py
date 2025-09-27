import gi
import logging
from typing import Any, Iterable, Optional, Union, Type, List
from gi.repository import Gtk  # pyright: ignore

gi.require_version("Gtk", "4.0")


class DataHelpers:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate_iterable(
        self,
        input_value: Any,
        name: str = "input",
        expected_length: Optional[int] = None,
        element_type: Optional[Union[Type, List[Type]]] = None,
        allow_empty: bool = True,
    ) -> bool:
        """
        Validate that the input is an iterable with optional constraints.
        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            expected_length (Optional[int]): Expected length of the iterable. If provided, must match exactly.
            element_type (Optional[Union[Type, List[Type]]]): Expected type(s) of elements in the iterable.
                - If a single type: all elements must be of this type.
                - If a list of types: each element must match the corresponding type by position.
            allow_empty (bool): Whether to allow empty iterables.
        Returns:
            bool: True if validation passes, False otherwise.
        """
        if not isinstance(input_value, Iterable):
            self.logger.warning(
                f"Invalid {name}: Expected an iterable, got {type(input_value).__name__}."
            )
            return False
        if isinstance(input_value, str):
            self.logger.warning(
                f"Invalid {name}: Strings are not considered valid iterables in this context."
            )
            return False
        try:
            iterator = list(input_value)
        except Exception:
            self.logger.warning(f"Invalid {name}: Could not iterate over input.")
            return False
        if not allow_empty and len(iterator) == 0:
            self.logger.warning(f"{name} cannot be empty.")
            return False
        if expected_length is not None and len(iterator) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected an iterable of length {expected_length}, got {len(iterator)}."
            )
            return False
        if element_type is not None:
            if isinstance(element_type, list):
                if len(element_type) != len(iterator):
                    self.logger.warning(
                        f"Invalid {name}: Number of element types ({len(element_type)}) "
                        f"does not match iterable length ({len(iterator)})."
                    )
                    return False
                for idx, (element, typ) in enumerate(zip(iterator, element_type)):
                    if not isinstance(element, typ):
                        self.logger.warning(
                            f"Invalid {name}: Element at index {idx} is not of type {typ.__name__}."
                        )
                        return False
            else:
                for idx, element in enumerate(iterator):
                    if not isinstance(element, element_type):
                        self.logger.warning(
                            f"Invalid {name}: Element at index {idx} is not of type {element_type.__name__}."
                        )
                        return False
        return True

    def validate_method(self, obj: Any, method_name: str) -> bool:
        """
        Validate that a method or attribute exists and is callable or a valid GTK widget.
        Args:
            obj (Any): The object to check.
            method_name (str): The name of the method or attribute to validate.
        Returns:
            bool: True if the method/attribute is callable or a valid GTK widget, False otherwise.
        """
        if not hasattr(obj, method_name):
            self.logger.warning(
                f"Object {obj.__class__.__name__} does not have '{method_name}'."
            )
            return False
        attr = getattr(obj, method_name)
        if callable(attr) or isinstance(attr, Gtk.Widget):
            return True
        self.logger.warning(
            f"'{method_name}' on {obj.__class__.__name__} is neither callable nor a valid GTK widget."
        )
        return False

    def validate_widget(self, widget: Any, name: str = "widget") -> bool:
        """
        Validate that the given object is a valid widget.
        Args:
            widget (Any): The object to validate.
            name (str): Name of the widget for logging purposes.
        Returns:
            bool: True if the widget is valid, False otherwise.
        """
        if not isinstance(widget, Gtk.Widget):
            self.logger.warning(f"{name} is not a valid Gtk.Widget.")
            return False
        return True

    def validate_string(
        self, input_value: Any, name: str = "input", allow_empty: bool = False
    ) -> bool:
        """
        Validate that the input is a non-empty string.
        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            allow_empty (bool): Whether to accept empty or whitespace-only strings.
        Returns:
            bool: True if valid, False otherwise.
        """
        if not isinstance(input_value, str):
            self.logger.warning(
                f"Invalid {name}: Expected a string, got {type(input_value).__name__}."
            )
            return False
        if not allow_empty and not input_value.strip():
            self.logger.warning(f"{name} cannot be empty.")
            return False
        return True

    def validate_integer(
        self,
        input_value: Any,
        name: str = "input",
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> bool:
        """
        Validate that the input is an integer within an optional range.
        Args:
            input_value (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            min_value (Optional[int]): Minimum allowed value (inclusive).
            max_value (Optional[int]): Maximum allowed value (inclusive).
        Returns:
            bool: True if valid, False otherwise.
        """
        if not isinstance(input_value, int):
            self.logger.warning(
                f"Invalid {name}: Expected an integer, got {type(input_value).__name__}."
            )
            return False
        if min_value is not None and input_value < min_value:
            self.logger.warning(f"{name} must be >= {min_value}.")
            return False
        if max_value is not None and input_value > max_value:
            self.logger.warning(f"{name} must be <= {max_value}.")
            return False
        return True

    def validate_tuple(
        self,
        input_value: Any,
        expected_length: Optional[int] = None,
        element_types: Optional[Union[Type, List[Type]]] = None,
        name: str = "input",
    ) -> bool:
        """
        Validate that the input is a tuple with optional type and length constraints.
        Args:
            input_value (Any): The value to validate.
            expected_length (Optional[int]): Expected length of the tuple. If provided, must match exactly.
            element_types (Optional[Union[Type, List[Type]]]): Expected type(s) of elements in the tuple.
                - If a single type: all elements must be of this type.
                - If a list of types: each element must match the corresponding type by position.
            name (str): Name of the input for logging purposes.
        Returns:
            bool: True if validation passes, False otherwise.
        """
        if not isinstance(input_value, tuple):
            self.logger.warning(
                f"Invalid {name}: Expected a tuple, got {type(input_value).__name__}."
            )
            return False
        if expected_length is not None and len(input_value) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected a tuple of length {expected_length}, got {len(input_value)}."
            )
            return False
        if element_types is not None:
            if isinstance(element_types, list):
                if len(element_types) != len(input_value):
                    self.logger.warning(
                        f"Invalid {name}: Number of element types ({len(element_types)}) "
                        f"does not match tuple length ({len(input_value)})."
                    )
                    return False
                for idx, (element, typ) in enumerate(zip(input_value, element_types)):
                    if not isinstance(element, typ):
                        self.logger.warning(
                            f"Invalid element type at index {idx} in {name}: "
                            f"Expected {typ.__name__}, got {type(element).__name__}."
                        )
                        return False
            elif isinstance(element_types, type):
                for idx, element in enumerate(input_value):
                    if not isinstance(element, element_types):
                        self.logger.warning(
                            f"Invalid element type at index {idx} in {name}: "
                            f"Expected {element_types.__name__}, got {type(element).__name__}."
                        )
                        return False
        return True

    def validate_bytes(
        self, input_value: Any, expected_length: int | None = None, name: str = "input"
    ) -> bool:
        """
        Validate that the input is a bytes object with optional length constraints.
        Args:
            input_value (Any): The value to validate.
            expected_length (Optional[int]): Expected length of the bytes object. If provided, must match exactly.
            name (str): Name of the input for logging purposes.
        Returns:
            bool: True if validation passes, False otherwise.
        """
        if not isinstance(input_value, bytes):
            self.logger.warning(
                f"Invalid {name}: Expected bytes, got {type(input_value).__name__}."
            )
            return False
        if expected_length is not None and len(input_value) != expected_length:
            self.logger.warning(
                f"Invalid {name}: Expected bytes of length {expected_length}, got {len(input_value)}."
            )
            return False
        return True

    def validate_list(
        self,
        input_list: Any,
        name: str = "input",
        element_type: Optional[Type] = None,
        allow_empty: bool = True,
    ) -> bool:
        """
        Validate that the input is a list with optional element type constraints.
        Args:
            input_list (Any): The value to validate.
            name (str): Name of the input for logging purposes.
            element_type (Optional[Type]): Expected type of each element in the list. If None, no type check is performed.
            allow_empty (bool): Whether to allow empty lists.
        Returns:
            bool: True if validation passes, False otherwise.
        """
        if not isinstance(input_list, list):
            self.logger.warning(
                f"Invalid {name}: Expected a list, got {type(input_list).__name__}."
            )
            return False
        if not allow_empty and not input_list:
            self.logger.warning(f"{name} cannot be empty.")
            return False
        if element_type is not None:
            for index, element in enumerate(input_list):
                if not isinstance(element, element_type):
                    self.logger.warning(
                        f"Invalid element type at index {index} in {name}: "
                        f"Expected {element_type.__name__}, got {type(element).__name__}."
                    )
                    return False
        return True
